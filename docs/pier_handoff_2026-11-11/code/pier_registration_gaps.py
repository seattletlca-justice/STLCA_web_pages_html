#!/usr/bin/env python3
"""
pier_registration_gaps.py  --  P.I.E.R. outputs A-F for RRIO registration lapses.
DRAFT, REVIEW REQUIRED.  Written 2026-11-11.  NOT YET RUN ON REAL DATA.
Tested only on the small, clearly labeled SAMPLE rows in ../tests/sample_data/.

What it builds (section 2 of docs/TRANSFER_DOC_PIER_2026-11-11.md):
  A  rrio_registration_periods        table + CSV
  B  rrio_registration_gaps           view  + CSV  (gaps starting on/after 2020-01-01)
  C  unregistered_candidates          view  + CSV
  D  evictions_without_registration   view  + CSV  (only if an eviction file is given)
  E  complaints_during_gaps           view  + CSV
  F  rrio_money_estimate              view  + CSV  (a CALCULATION, not money owed)

It writes a NEW SQLite file (default pier_registration_gaps_DRAFT.sqlite).
It does NOT open, change, or replace stlca_property_intelligence.sqlite.
Folding these tables into P.I.E.R. itself needs Kimberly's approval.

Rules built into the code:
  * Unknown column headers stop the run with an error that lists them.  Nothing is guessed.
    Known headers come from the Drive "Traceability Document: Merging Seattle Rental
    Property Registration and RRIO Datasets" and the P.I.E.R. skill.  If a real file has
    other headers, add them to the maps below on purpose, or pass --ignore-columns.
  * Nothing that expires on or after --data-end (default 2025-11-20, the newest RRIO data)
    is called lapsed.  Those rows get status "expires after data end - unknown".
  * A registration with no known expiration date ends in "coverage unknown", not a gap,
    unless --assumed-term-years is given.  Any period built from that assumption is
    labeled end_date_basis = "ESTIMATED".
  * A failed address match is not proof a property is unregistered.  Every output says so.
  * Every row keeps the source file and row number of each date it uses.

Run (from the folder that holds the files), for example:
  python pier_registration_gaps.py --check-headers --rrio-dir . --snapshot-dir .
  python pier_registration_gaps.py --rrio-dir . --snapshot-dir . \
      --complaints MASTER_SOURCE_CITYWIDE_LLT_....csv \
      --fee-schedule fee_schedule_RRIO.json --out-dir pier_gaps_out
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

csv.field_size_limit(10_000_000)

# ---------------------------------------------------------------- header maps
# Key = header upper-cased with every non-letter/digit removed.
# RRIO RecordList exports.  Sources:
#   Drive Traceability Document, section 2: DATE, RECORDNUMBER, RECORDTYPE, PRIVATEINSPECTOR,
#     STATUSCURRENT, REGISTRATIONEXPIRED, ORIGINALADDRESS1 (+ empty unnamed columns)
#   Same document, 2023 file load log: date, record_type, private_inspector, status_current,
#     registration_expired, address   (this file had NO record number column)
#   stlca-property-intelligence-db skill: Create Date, Record Number, Record Type, Status, Address
RRIO_HEADER_MAP = {
    "DATE": "event_date", "CREATEDATE": "event_date",
    "RECORDNUMBER": "record_number",
    "RECORDTYPE": "record_type",
    "PRIVATEINSPECTOR": "private_inspector",
    "STATUSCURRENT": "status", "STATUS": "status",
    "REGISTRATIONEXPIRED": "registration_expired",
    "ORIGINALADDRESS1": "address", "ADDRESS": "address",
}
RRIO_REQUIRED = ("event_date", "record_type", "address")

# Rental Property Registration snapshots.  Sources:
#   Drive Traceability Document, section 2: REGISTRATIONNUMBER, UNITS, PROPERTYNAME,
#     REGISTEREDDATE, EXPIRESDATE, STATUSCURRENT, ORIGINALADDRESS1, ORIGINALZIP,
#     PROPERTYCONTACTNAME, LATITUDE, LONGITUDE
#   stlca-property-crossref skill (Open Data names): RegistrationNum, RentalHousingUnits,
#     PropertyName, RegisteredDate, ExpiresDate, StatusCurrent, OriginalAddress1, OriginalZip,
#     PropertyContactName
SNAP_HEADER_MAP = {
    "REGISTRATIONNUMBER": "regnum", "REGISTRATIONNUM": "regnum",
    "UNITS": "units", "RENTALHOUSINGUNITS": "units",
    "PROPERTYNAME": "property_name",
    "REGISTEREDDATE": "registered_date",
    "EXPIRESDATE": "expires_date",
    "STATUSCURRENT": "status",
    "ORIGINALADDRESS1": "address",
    "ORIGINALZIP": "zip",
    "PROPERTYCONTACTNAME": "contact",
    "LATITUDE": "lat", "LONGITUDE": "lon",
}
SNAP_REQUIRED = ("regnum", "expires_date", "address")

# Landlord-tenant master (input/ copy, checked 2026-11-11): only these columns are used.
COMPLAINT_COLUMNS = ("RECORDNUM", "RECORDTYPE", "OPENDATE", "ORIGINALADDRESS1", "DISTRICT", "CP", "VI", "CT")

# RRIO record types (values, upper-cased), from the P.I.E.R. skill's observed list 2015-2025.
T_REG = {"RENTAL PROPERTY REGISTRATION", "RENTAL PROPERTY RENEWAL"}
T_TRANSFER = {"TRANSFER EXISTING REGISTRATION TO NEW OWNERS"}
T_LATE = {"RENTAL PROPERTY LATE REGISTRATION VIOLATION"}
T_VIOL = {"RENTAL PROPERTY VIOLATION"}
T_INSPECT = {"RENTAL PROPERTY INSPECTION REQUIREMENT", "RENTAL PROPERTY INSPECTION - PRIVATE INSPECTOR"}
T_NOT_PROPERTY = {"PRIVATE INSPECTOR REGISTRATION", "PRIVATE INSPECTOR RENEWAL"}
KNOWN_TYPES = T_REG | T_TRANSFER | T_LATE | T_VIOL | T_INSPECT | T_NOT_PROPERTY

VALID_RECORDNUM = re.compile(r"^\d{3}-\d{7}")  # Traceability doc: keep XXX-XXXXXXX numbers

GAP_SINCE = "2020-01-01"
UNMATCHED_NOTE = "A failed address match is not proof a property is unregistered."


class HeaderError(Exception):
    pass


# ---------------------------------------------------------------- helpers
def hkey(h):
    return re.sub(r"[^A-Z0-9]", "", (h or "").upper())


def normalize_address(addr):
    """P.I.E.R. normalization: capitals, single spaces, drop trailing period,
    drop a trailing ' SEATTLE' (RRIO exports append it inconsistently)."""
    if not addr:
        return ""
    a = re.sub(r"\s+", " ", addr.strip().upper()).rstrip(".").rstrip(",").strip()
    a = re.sub(r",?\s+SEATTLE$", "", a).strip()
    return a.rstrip(".").rstrip(",").strip()


_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%Y-%m-%d",
                 "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y %b %d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S")


def parse_date(s):
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def iso(d):
    return d.isoformat() if d else ""


def to_int(s):
    try:
        return int(float(str(s).strip()))
    except (TypeError, ValueError):
        return None


def open_text(path, allow_cp1252, log):
    """Read whole file as text. Bad bytes stop the run unless --allow-cp1252-fallback."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        if not allow_cp1252:
            raise HeaderError(f"{os.path.basename(path)}: not valid UTF-8 ({e}). "
                              "Re-save it as UTF-8, or re-run with --allow-cp1252-fallback (logged).")
        log(f"WARNING {os.path.basename(path)}: not valid UTF-8 ({e}); decoded as cp1252 instead.")
        return raw.decode("cp1252", errors="strict")


def map_headers(path, headers, header_map, required, ignore, text_rows):
    """Return {raw_header: canonical}. Raise HeaderError on unknown or missing headers."""
    mapping, unknown = {}, []
    for h in headers:
        k = hkey(h)
        if k in header_map:
            mapping[h] = header_map[k]
        elif k == "" or k.startswith("UNNAMED"):
            # empty header: only allowed if every value in that column is blank
            idx = headers.index(h)
            if any(len(r) > idx and r[idx].strip() for r in text_rows):
                unknown.append(f"(unnamed column {idx + 1} has values)")
        elif h in ignore or k in {hkey(x) for x in ignore}:
            continue
        else:
            unknown.append(h)
    if unknown:
        raise HeaderError(f"{os.path.basename(path)}: unknown column header(s): {unknown}. "
                          "Not guessed. Add them to the header map on purpose, or list them in --ignore-columns.")
    have = set(mapping.values())
    missing = [c for c in required if c not in have]
    if missing:
        raise HeaderError(f"{os.path.basename(path)}: required column(s) missing: {missing}. Headers found: {headers}")
    return mapping


def read_mapped(path, header_map, required, ignore, allow_cp1252, log):
    text = open_text(path, allow_cp1252, log)
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise HeaderError(f"{os.path.basename(path)}: empty file")
    headers, body = rows[0], rows[1:]
    mapping = map_headers(path, headers, header_map, required, ignore, body)
    out = []
    for i, r in enumerate(body, start=2):  # row 1 is the header
        rec = {"_file": os.path.basename(path), "_row": i}
        for j, h in enumerate(headers):
            if h in mapping and j < len(r):
                rec[mapping[h]] = r[j].strip()
        out.append(rec)
    return out, mapping


# ---------------------------------------------------------------- loaders
def load_rrio(files, ignore, allow_cp1252, log):
    events, problems = [], []
    unknown_types = defaultdict(int)
    for f in files:
        try:
            rows, mapping = read_mapped(f, RRIO_HEADER_MAP, RRIO_REQUIRED, ignore, allow_cp1252, log)
        except HeaderError as e:
            problems.append(str(e))
            continue
        has_recnum = "record_number" in mapping.values()
        if not has_recnum:
            log(f"WARNING {os.path.basename(f)}: no record number column; its events match by address only.")
        kept = bad_date = blank_addr = bad_num = 0
        for r in rows:
            if has_recnum and not VALID_RECORDNUM.match(r.get("record_number", "")):
                bad_num += 1  # footer / junk lines (Traceability doc rule)
                continue
            d = parse_date(r.get("event_date"))
            na = normalize_address(r.get("address"))
            if not na:
                blank_addr += 1
                continue
            if d is None:
                bad_date += 1
                continue
            rt = (r.get("record_type") or "").strip().upper()
            if rt not in KNOWN_TYPES:
                unknown_types[rt] += 1
            events.append({
                "normalized_address": na, "event_date": iso(d), "record_type": rt,
                "record_number": r.get("record_number", ""), "status": r.get("status", ""),
                "private_inspector": r.get("private_inspector", ""),
                "registration_expired": r.get("registration_expired", ""),
                "source_file": r["_file"], "source_row": r["_row"],
            })
            kept += 1
        log(f"RRIO {os.path.basename(f)}: {len(rows)} rows read, {kept} kept, "
            f"{bad_num} no valid record number, {blank_addr} blank address, {bad_date} unreadable date")
        if kept == 0:
            log(f"WARNING {os.path.basename(f)}: 0 valid rows. Not dropped silently - check this file.")
    for t, n in sorted(unknown_types.items(), key=lambda x: -x[1]):
        log(f"NOTE RRIO record type not in the known list (kept, not used for periods): {t!r} x{n}")
    return events, problems


def load_snapshots(files, ignore, allow_cp1252, log):
    rows_out, problems = [], []
    for f in files:
        try:
            rows, _ = read_mapped(f, SNAP_HEADER_MAP, SNAP_REQUIRED, ignore, allow_cp1252, log)
        except HeaderError as e:
            problems.append(str(e))
            continue
        kept = bad = 0
        for r in rows:
            na = normalize_address(r.get("address"))
            exp = parse_date(r.get("expires_date"))
            if not na or not r.get("regnum") or exp is None:
                bad += 1
                continue
            rows_out.append({
                "normalized_address": na, "regnum": r["regnum"].strip(),
                "registered_date": iso(parse_date(r.get("registered_date"))), "expires_date": iso(exp),
                "units": to_int(r.get("units")), "lat": r.get("lat", ""), "lon": r.get("lon", ""),
                "property_name": r.get("property_name", ""), "zip": r.get("zip", ""),
                "source_file": r["_file"], "source_row": r["_row"],
            })
            kept += 1
        log(f"SNAPSHOT {os.path.basename(f)}: {len(rows)} rows read, {kept} kept, "
            f"{bad} missing address / registration number / readable expiration date")
        if kept == 0:
            log(f"WARNING {os.path.basename(f)}: 0 valid rows. Not dropped silently - check this file.")
    return rows_out, problems


def load_complaints(path, topics_path, allow_cp1252, log):
    text = open_text(path, allow_cp1252, log)
    rdr = csv.DictReader(text.splitlines())
    missing = [c for c in COMPLAINT_COLUMNS if c not in (rdr.fieldnames or [])]
    if missing:
        raise HeaderError(f"{os.path.basename(path)}: required column(s) missing: {missing}")
    rent = {}
    if topics_path:
        trdr = csv.DictReader(open_text(topics_path, allow_cp1252, log).splitlines())
        need = ("record_number", "topic_rent_increases_and_fees")
        if any(c not in (trdr.fieldnames or []) for c in need):
            raise HeaderError(f"{os.path.basename(topics_path)}: needs columns {need}")
        for t in trdr:
            rent[t["record_number"].strip()] = t["topic_rent_increases_and_fees"].strip().lower() == "yes"
    out, blank = [], 0
    for i, r in enumerate(rdr, start=2):
        na = normalize_address(r["ORIGINALADDRESS1"])
        od = parse_date(r["OPENDATE"])
        if not na or od is None:
            blank += 1
            continue
        rn = r["RECORDNUM"].strip()
        out.append({
            "record_num": rn, "normalized_address": na, "open_date": iso(od),
            "record_type": r["RECORDTYPE"].strip().upper(), "district": r["DISTRICT"].strip(),
            "is_complaint": int(r["CP"].strip().upper() == "TRUE"),
            "is_violation": int(r["VI"].strip().upper() == "TRUE" or r["CT"].strip().upper() == "TRUE"),
            "is_rent_increase": (None if not topics_path else int(rent.get(rn, False))),
            "source_file": os.path.basename(path), "source_row": i,
        })
    log(f"COMPLAINTS {os.path.basename(path)}: {len(out)} kept, {blank} blank address or unreadable date"
        + ("" if topics_path else "; no topics file given, so rent-increase flag is left blank"))
    return out


def load_by_named_columns(path, cols, label, allow_cp1252, log):
    """For files whose headers are not known here (eviction file, King County file).
    Column names must be given on the command line; a missing one stops the run."""
    rdr = csv.DictReader(open_text(path, allow_cp1252, log).splitlines())
    missing = [c for c in cols.values() if c and c not in (rdr.fieldnames or [])]
    if missing:
        raise HeaderError(f"{label} {os.path.basename(path)}: column(s) {missing} not found. Headers: {rdr.fieldnames}")
    return [(i, r) for i, r in enumerate(rdr, start=2)]


# ---------------------------------------------------------------- output A: periods
def build_periods(snap_rows, events, data_end, term_years):
    """One row per registration period per address.
    Snapshot periods: one per (address, registration number, expiration date).
    RRIO registration/renewal events that fall inside a snapshot period are attached to it;
    the rest become their own periods with an unknown end (or ESTIMATED end if term_years)."""
    periods = []
    by_key = {}
    for s in snap_rows:
        k = (s["normalized_address"], s["regnum"], s["expires_date"])
        p = by_key.get(k)
        if p is None:
            p = by_key[k] = {
                "normalized_address": s["normalized_address"], "registration_number": s["regnum"],
                "start_date": s["registered_date"], "start_basis": "SNAPSHOT_REGISTEREDDATE",
                "start_source": f'{s["source_file"]}:{s["source_row"]}' if s["registered_date"] else "",
                "end_date": s["expires_date"], "end_date_basis": "SNAPSHOT_EXPIRESDATE",
                "end_source": f'{s["source_file"]}:{s["source_row"]}',
                "units": s["units"], "rrio_events_attached": 0, "_events": [],
            }
            periods.append(p)
        else:
            if s["registered_date"] and (not p["start_date"] or s["registered_date"] < p["start_date"]):
                p["start_date"] = s["registered_date"]
                p["start_source"] = f'{s["source_file"]}:{s["source_row"]}'
            if s["units"] is not None and (p["units"] is None or s["units"] > p["units"]):
                p["units"] = s["units"]
    by_addr = defaultdict(list)
    for p in periods:
        by_addr[p["normalized_address"]].append(p)

    for e in events:
        if e["record_type"] not in T_REG:
            continue
        host = None
        for p in by_addr.get(e["normalized_address"], []):
            if e["record_number"] and e["record_number"] == p["registration_number"]:
                host = p
                break
            lo = p["start_date"] or "0000-00-00"
            if lo <= e["event_date"] <= p["end_date"]:
                host = host or p
        if host is not None:
            host["rrio_events_attached"] += 1
            if not host["start_date"] or e["event_date"] < host["start_date"]:
                host["start_date"], host["start_basis"] = e["event_date"], "RRIO_EVENT_DATE"
                host["start_source"] = f'{e["source_file"]}:{e["source_row"]}'
            continue
        end, basis = "", "UNKNOWN"
        if term_years:
            d = dt.date.fromisoformat(e["event_date"])
            try:
                end = iso(d.replace(year=d.year + term_years))
            except ValueError:  # Feb 29
                end = iso(d.replace(year=d.year + term_years, day=28))
            basis = f"ESTIMATED_EVENT_DATE_PLUS_{term_years}_YEARS"
        p = {
            "normalized_address": e["normalized_address"], "registration_number": e["record_number"],
            "start_date": e["event_date"], "start_basis": "RRIO_EVENT_DATE",
            "start_source": f'{e["source_file"]}:{e["source_row"]}',
            "end_date": end, "end_date_basis": basis, "end_source": "",
            "units": None, "rrio_events_attached": 1, "_events": [],
        }
        periods.append(p)
        by_addr[e["normalized_address"]].append(p)

    de = iso(data_end)
    for p in periods:
        if not p["end_date"]:
            p["end_status"] = "end date unknown"
        elif p["end_date"] >= de:
            p["end_status"] = "expires after data end - unknown"
        else:
            p["end_status"] = "expired before data end"
        p.pop("_events", None)
    return periods


# ---------------------------------------------------------------- gaps (all years)
def build_gaps(periods, events, data_end):
    """A gap = time between one period's expiration and the next registration/renewal start
    at the same address.  Only expirations BEFORE data_end can open a gap."""
    de = iso(data_end)
    by_addr = defaultdict(list)
    for p in periods:
        if p["start_date"] or p["end_date"]:
            by_addr[p["normalized_address"]].append(p)
    ev_by_addr = defaultdict(list)
    for e in events:
        ev_by_addr[e["normalized_address"]].append(e)

    gaps, unknown_segments = [], []
    for addr, plist in by_addr.items():
        plist.sort(key=lambda p: (p["start_date"] or p["end_date"], p["end_date"] or "9999"))
        units = max([p["units"] for p in plist if p["units"] is not None], default=None)
        cover_end, cover_src, cover_reg = None, "", ""
        known = True
        first = True
        for p in plist:
            start = p["start_date"] or p["end_date"]
            if first:
                first = False
            elif not p["start_date"]:
                # start date not on file: we cannot say when coverage resumed, so no gap is opened
                unknown_segments.append({"normalized_address": addr, "from_period_start": "", "until": p["end_date"],
                                         "reason": "next period has no known start date"})
            elif not known:
                unknown_segments.append({"normalized_address": addr, "from_period_start": "", "until": start,
                                         "reason": "earlier period has no known end date"})
            elif cover_end and start > cover_end:
                gaps.append(_gap(addr, cover_end, start, cover_src, cover_reg, p, units, ev_by_addr[addr], de))
            if p["end_date"]:
                if known and cover_end and cover_end > p["end_date"]:
                    pass  # earlier coverage already runs longer
                else:
                    cover_end, cover_src, cover_reg = p["end_date"], p["end_source"] or p["end_date_basis"], p["registration_number"]
                known = True
            else:
                known = False
        if known and cover_end and cover_end < de:
            gaps.append(_gap(addr, cover_end, None, cover_src, cover_reg, None, units, ev_by_addr[addr], de))
        if not known:
            unknown_segments.append({"normalized_address": addr, "from_period_start": plist[-1]["start_date"],
                                     "until": de, "reason": "last period has no known end date"})
    return gaps, unknown_segments


def _gap(addr, gap_start, next_start, end_src, regnum, next_p, units, evs, de):
    win_end = next_start or de
    lrv = [e for e in evs if e["record_type"] in T_LATE and gap_start <= e["event_date"] <= win_end]
    exp_rows = [e for e in evs if gap_start <= e["event_date"] <= win_end
                and ("EXPIRED" in e["status"].upper() or e["registration_expired"].strip().upper() in ("TRUE", "YES", "Y", "1"))]
    transfers = [e for e in evs if e["record_type"] in T_TRANSFER and gap_start <= e["event_date"] <= win_end]
    days = (dt.date.fromisoformat(win_end) - dt.date.fromisoformat(gap_start)).days
    return {
        "normalized_address": addr, "registration_number_before_gap": regnum,
        "gap_start": gap_start, "gap_start_source": end_src,
        "gap_end": next_start or "", "gap_end_source": (next_p["start_source"] if next_p else ""),
        "gap_status": "closed by later registration or renewal" if next_start else f"still open as of {de}",
        "gap_days": days, "later_renewed": int(bool(next_start)), "units": units,
        "late_registration_violation_count": len(lrv),
        "late_registration_violation_records": ";".join(e["record_number"] or f'{e["source_file"]}:{e["source_row"]}' for e in lrv),
        "late_violation_same_regnum": int(any(regnum and e["record_number"] == regnum for e in lrv)),
        "registration_expired_status_rows": len(exp_rows),
        "transfer_events_in_gap": len(transfers),
        "data_end_date": de,
    }


# ---------------------------------------------------------------- district
def district_lookup(snap_rows, complaints, geojson):
    """District per address: point-in-polygon on snapshot lat/lon if --districts-geojson
    and shapely are available; else the first DISTRICT value in the complaints master."""
    out, src = {}, {}
    if geojson:
        try:
            from shapely.geometry import Point, shape
        except ImportError:
            raise SystemExit("--districts-geojson needs shapely: pip install shapely")
        with open(geojson, encoding="utf-8") as fh:
            feats = [(f["properties"]["C_DISTRICT"], shape(f["geometry"])) for f in json.load(fh)["features"]]
        for s in snap_rows:
            if s["normalized_address"] in out:
                continue
            try:
                pt = Point(float(s["lon"]), float(s["lat"]))  # GeoJSON order is (lon, lat)
            except (TypeError, ValueError):
                continue
            for name, poly in feats:
                if poly.contains(pt):
                    out[s["normalized_address"]], src[s["normalized_address"]] = str(name), "geojson point-in-polygon"
                    break
    for c in complaints:
        if c["normalized_address"] not in out and c["district"]:
            out[c["normalized_address"]], src[c["normalized_address"]] = c["district"], "complaints master DISTRICT"
    return out, src


# ---------------------------------------------------------------- output C evidence
def build_candidates(snap_rows, events, complaints, reg03_path, kc_rows, kc_cols, min_units, allow_cp1252, log):
    registered = {s["normalized_address"] for s in snap_rows} | {e["normalized_address"] for e in events if e["record_type"] in T_REG}
    any_rrio = registered | {e["normalized_address"] for e in events}
    ev = defaultdict(lambda: defaultdict(list))
    if kc_rows is not None:
        for i, r in kc_rows:
            na = normalize_address(r[kc_cols["address"]])
            u = to_int(r[kc_cols["units"]]) if kc_cols.get("units") else None
            if not na or na in registered:
                continue
            if min_units is not None and (u is None or u < min_units):
                continue
            ev[na]["king_county_parcel_no_rrio"].append(f"row {i}" + (f" units={u}" if u is not None else ""))
    for c in complaints:
        if c["normalized_address"] not in any_rrio:
            ev[c["normalized_address"]]["lt_record_no_rrio_match"].append(c["record_num"])
    if reg03_path:
        rdr = csv.DictReader(open_text(reg03_path, allow_cp1252, log).splitlines())
        for c in ("record_num", "address", "matched_phrase"):
            if c not in (rdr.fieldnames or []):
                raise HeaderError(f"{os.path.basename(reg03_path)}: column {c!r} missing")
        for r in rdr:
            na = normalize_address(r["address"])
            if na:
                ev[na]["reg03_complaint_says_unregistered"].append(f'{r["record_num"]} ({r["matched_phrase"]})')
    for e in events:
        if e["record_type"] in (T_VIOL | T_LATE) and e["normalized_address"] not in registered:
            ev[e["normalized_address"]]["rrio_violation_no_registration_on_file"].append(e["record_number"] or e["record_type"])
    out = []
    for na, d in ev.items():
        out.append({
            "normalized_address": na,
            "has_any_rrio_registration_on_file": int(na in registered),
            "has_any_rrio_record_on_file": int(na in any_rrio),
            "evidence_kinds": ";".join(sorted(d)),
            "evidence_kind_count": len(d),
            "king_county_parcel_no_rrio": "; ".join(d.get("king_county_parcel_no_rrio", [])),
            "lt_records_no_rrio_match": "; ".join(d.get("lt_record_no_rrio_match", [])[:25]),
            "lt_record_count": len(d.get("lt_record_no_rrio_match", [])),
            "reg03_complaints": "; ".join(d.get("reg03_complaint_says_unregistered", [])),
            "rrio_violations_no_registration": "; ".join(d.get("rrio_violation_no_registration_on_file", [])),
            "note": "Lead for review only. " + UNMATCHED_NOTE + " Owner-occupied and exempt housing not yet checked.",
        })
    return out


# ---------------------------------------------------------------- SQLite + views
VIEWS_SQL = f"""
-- B. rrio_registration_gaps: every gap that STARTED on or after {GAP_SINCE}.
--    gap_start = the expiration date of the last known period; gap_end = start of the next
--    registration/renewal at the same address, or blank if still open as of data_end_date.
--    Limitation: address-only join (one address can be several buildings, and vice versa).
DROP VIEW IF EXISTS rrio_registration_gaps;
CREATE VIEW rrio_registration_gaps AS
SELECT g.*, COALESCE(d.district, '') AS district, COALESCE(d.district_source, '') AS district_source
FROM rrio_gaps_all g LEFT JOIN address_district d ON d.normalized_address = g.normalized_address
WHERE g.normalized_address != '' AND g.gap_start >= '{GAP_SINCE}';

-- C. unregistered_candidates: addresses with evidence they may be rentals but no RRIO
--    registration on file at any time (plus REG-03 complaint addresses, flagged either way).
--    Each row is a LEAD. A failed address match is not proof of anything.
DROP VIEW IF EXISTS unregistered_candidates;
CREATE VIEW unregistered_candidates AS
SELECT c.*, COALESCE(d.district, '') AS district FROM candidate_evidence c
LEFT JOIN address_district d ON d.normalized_address = c.normalized_address
WHERE c.normalized_address != '';

-- E. complaints_during_gaps: complaints, violations (NOV + citation) and rent-increase
--    complaints whose OPEN date falls inside a gap from view B.
--    Gap window: gap_start <= open_date < gap_end (or <= data_end_date when still open).
DROP VIEW IF EXISTS complaints_during_gaps;
CREATE VIEW complaints_during_gaps AS
SELECT c.record_num, c.record_type, c.open_date, c.is_complaint, c.is_violation, c.is_rent_increase,
       g.normalized_address, g.gap_start, g.gap_end, g.gap_status, g.gap_days, g.units, g.district,
       c.source_file, c.source_row
FROM lt_complaints c
JOIN rrio_registration_gaps g ON g.normalized_address = c.normalized_address
WHERE c.normalized_address != ''
  AND c.open_date >= g.gap_start
  AND ( (g.gap_end != '' AND c.open_date < g.gap_end)
     OR (g.gap_end = '' AND c.open_date <= g.data_end_date) );

-- F. rrio_money_estimate: a CALCULATION from the fee schedule table, not a record of money owed.
--    registration_fee_calc = (number of {{term_days}}-day terms the gap spans, rounded up)
--                            x (property fee + per-unit fee x (units - 1)).
--    Units unknown -> property fee only, flagged.  Fee row = the schedule in effect on gap_start.
--    late_fees_schedule_would_apply = late-registration-violation events in the gap x late fee.
--    The data does not show whether any fee was charged or paid.
DROP VIEW IF EXISTS rrio_money_estimate;
CREATE VIEW rrio_money_estimate AS
SELECT g.normalized_address, g.district, g.gap_start, g.gap_end, g.gap_status,
       CAST(g.gap_days AS INTEGER) AS gap_days, g.units,
       f.schedule_label, f.verified,
       (CAST(g.gap_days AS INTEGER) + CAST(f.term_days AS INTEGER) - 1) / CAST(f.term_days AS INTEGER) AS terms_spanned,
       ((CAST(g.gap_days AS INTEGER) + CAST(f.term_days AS INTEGER) - 1) / CAST(f.term_days AS INTEGER))
         * (CAST(f.property_fee AS REAL)
            + CAST(f.additional_unit_fee AS REAL) * MAX(COALESCE(CAST(g.units AS INTEGER), 1) - 1, 0)) AS registration_fee_calc,
       CASE WHEN g.units IS NULL OR g.units = '' THEN 'units unknown - property fee only' ELSE '' END AS units_note,
       CAST(g.late_registration_violation_count AS INTEGER) AS late_registration_events,
       CAST(g.late_registration_violation_count AS INTEGER) * CAST(f.late_fee AS REAL) AS late_fees_schedule_would_apply,
       'CALCULATION ONLY - not a record of money owed, charged or unpaid' AS label
FROM rrio_registration_gaps g
JOIN fee_schedule f ON f.effective_from = (
     SELECT MAX(f2.effective_from) FROM fee_schedule f2 WHERE f2.effective_from <= g.gap_start)
WHERE CAST(g.gap_days AS INTEGER) > 0;
"""

EVICTION_VIEW_SQL = """
-- D. evictions_without_registration: each eviction filing matched to RRIO status on its filing date.
--    covered                      a known period runs from start <= filing_date <= end
--    in_gap                       inside a gap (any year) at that address
--    before_first_registration    the address has RRIO periods, all starting after the filing
--    undetermined                 address registered but coverage on that date is unknown
--                                 (period with no end date, or filing after data_end_date)
--    never_registered_on_file     no RRIO registration of any kind at that address
--    could_not_match              blank address or unreadable filing date
--    Wording rule: report counts as "N filings at addresses with no RRIO registration on file
--    on the filing date, based on the records reviewed". Never "should not have been evicted".
DROP VIEW IF EXISTS evictions_without_registration;
CREATE VIEW evictions_without_registration AS
SELECT e.*,
  CASE
    WHEN e.normalized_address = '' OR e.filing_date = '' THEN 'could_not_match'
    WHEN e.filing_date > (SELECT MAX(data_end_date) FROM rrio_gaps_meta) THEN 'undetermined'
    WHEN EXISTS (SELECT 1 FROM rrio_registration_periods p WHERE p.normalized_address = e.normalized_address
                 AND p.start_date != '' AND p.end_date != ''
                 AND p.start_date <= e.filing_date AND e.filing_date <= p.end_date) THEN 'covered'
    WHEN EXISTS (SELECT 1 FROM rrio_gaps_all g WHERE g.normalized_address = e.normalized_address
                 AND g.gap_start < e.filing_date
                 AND (g.gap_end = '' OR e.filing_date < g.gap_end)) THEN 'in_gap'
    WHEN NOT EXISTS (SELECT 1 FROM rrio_registration_periods p WHERE p.normalized_address = e.normalized_address)
         THEN 'never_registered_on_file'
    WHEN NOT EXISTS (SELECT 1 FROM rrio_registration_periods p WHERE p.normalized_address = e.normalized_address
                     AND COALESCE(NULLIF(p.start_date, ''), p.end_date) <= e.filing_date)
         THEN 'before_first_registration'
    ELSE 'undetermined'
  END AS rrio_status_on_filing_date,
  (SELECT MAX(CAST(p.units AS INTEGER)) FROM rrio_registration_periods p
     WHERE p.normalized_address = e.normalized_address) AS units_on_file
FROM evictions e;
"""


def write_log(out_dir, lines):
    with open(os.path.join(out_dir, "RUN_LOG.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_table(conn, name, rows, cols):
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute(f"CREATE TABLE {name} ({', '.join(c + ' TEXT' for c in cols)})")
    conn.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})",
                     [[("" if r.get(c) is None else r.get(c)) for c in cols] for r in rows])
    conn.execute(f"CREATE INDEX IF NOT EXISTS ix_{name}_addr ON {name}(normalized_address)") \
        if "normalized_address" in cols else None


def export(conn, name, out_dir):
    cur = conn.execute(f"SELECT * FROM {name}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    path = os.path.join(out_dir, f"{name}_DRAFT.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rrio-dir", help="folder with RRIO_*RecordList*.csv and 'RRIO 2015-1016.csv'")
    ap.add_argument("--rrio-glob", default="RRIO*.csv")
    ap.add_argument("--snapshot-dir", help="folder with Rental_Property_Registration_*.csv")
    ap.add_argument("--snapshot-glob", default="Rental_Property_Registration_*.csv")
    ap.add_argument("--exclude", default="", help="comma list of file names to skip (each is logged)")
    ap.add_argument("--ignore-columns", default="", help="comma list of extra headers to ignore on purpose")
    ap.add_argument("--allow-cp1252-fallback", action="store_true")
    ap.add_argument("--check-headers", action="store_true", help="only check every file's headers, then stop")
    ap.add_argument("--data-end", default="2025-11-20", help="newest date the RRIO data covers")
    ap.add_argument("--assumed-term-years", type=int, default=None,
                    help="OFF by default. If set, registrations with no known expiration get an ESTIMATED end")
    ap.add_argument("--complaints", help="landlord-tenant master CSV")
    ap.add_argument("--topics", help="landlord-tenant-records.csv (record_number, topic_rent_increases_and_fees)")
    ap.add_argument("--reg03", help="REG03_unregistered_or_lapsed_complaints_2020_2025_DRAFT.csv")
    ap.add_argument("--kc-file"); ap.add_argument("--kc-address-col"); ap.add_argument("--kc-units-col")
    ap.add_argument("--min-units", type=int, default=None, help="apartment cutoff (Kimberly decides)")
    ap.add_argument("--evictions"); ap.add_argument("--evictions-address-col"); ap.add_argument("--evictions-date-col")
    ap.add_argument("--evictions-id-col")
    ap.add_argument("--fee-schedule", help="JSON fee schedule (see fee_schedule_RRIO.json)")
    ap.add_argument("--districts-geojson")
    ap.add_argument("--out-dir", default="pier_gaps_out")
    ap.add_argument("--sqlite", default=None, help="default <out-dir>/pier_registration_gaps_DRAFT.sqlite")
    a = ap.parse_args(argv)

    os.makedirs(a.out_dir, exist_ok=True)
    log_lines = []

    def log(s):
        print(s)
        log_lines.append(s)

    log(f"pier_registration_gaps.py run {dt.datetime.now().isoformat(timespec='seconds')}  DRAFT, REVIEW REQUIRED")
    data_end = dt.date.fromisoformat(a.data_end)
    exclude = {x.strip() for x in a.exclude.split(",") if x.strip()}
    ignore = [x.strip() for x in a.ignore_columns.split(",") if x.strip()]

    def files(d, pattern):
        if not d:
            return []
        fs = sorted(glob.glob(os.path.join(d, pattern)))
        for f in fs:
            if os.path.basename(f) in exclude:
                log(f"EXCLUDED on request: {os.path.basename(f)}")
        return [f for f in fs if os.path.basename(f) not in exclude]

    rrio_files = files(a.rrio_dir, a.rrio_glob)
    snap_files = files(a.snapshot_dir, a.snapshot_glob)
    log(f"Found {len(rrio_files)} RRIO files, {len(snap_files)} snapshot files")

    events, p1 = load_rrio(rrio_files, ignore, a.allow_cp1252_fallback, log)
    snaps, p2 = load_snapshots(snap_files, ignore, a.allow_cp1252_fallback, log)
    problems = p1 + p2
    if problems:
        log("STOPPED: header or encoding problems (nothing was guessed):")
        for p in problems:
            log("  - " + p)
        write_log(a.out_dir, log_lines)
        return 2
    if a.check_headers:
        log("Header check passed for every file.")
        write_log(a.out_dir, log_lines)
        return 0

    late = [e for e in events if e["event_date"] > iso(data_end)]
    if late:
        log(f"WARNING {len(late)} RRIO events are dated after --data-end {data_end}. Check --data-end.")

    complaints = load_complaints(a.complaints, a.topics, a.allow_cp1252_fallback, log) if a.complaints else []

    periods = build_periods(snaps, events, data_end, a.assumed_term_years)
    gaps, unknown = build_gaps(periods, events, data_end)
    log(f"A periods: {len(periods)} rows over {len({p['normalized_address'] for p in periods})} addresses")
    log(f"gaps (all years): {len(gaps)}; coverage-unknown segments: {len(unknown)}")

    kc_rows, kc_cols = None, {}
    if a.kc_file:
        if not a.kc_address_col:
            raise SystemExit("--kc-file needs --kc-address-col (its headers are not known here)")
        kc_cols = {"address": a.kc_address_col, "units": a.kc_units_col}
        kc_rows = load_by_named_columns(a.kc_file, kc_cols, "King County", a.allow_cp1252_fallback, log)
    cands = build_candidates(snaps, events, complaints, a.reg03, kc_rows, kc_cols, a.min_units,
                             a.allow_cp1252_fallback, log)
    dist, dsrc = district_lookup(snaps, complaints, a.districts_geojson)

    sq = a.sqlite or os.path.join(a.out_dir, "pier_registration_gaps_DRAFT.sqlite")
    if os.path.basename(sq) == "stlca_property_intelligence.sqlite":
        raise SystemExit("Refusing to write into the P.I.E.R. database itself. That needs Kimberly's approval.")
    conn = sqlite3.connect(sq)
    write_table(conn, "rrio_events", events, ["normalized_address", "event_date", "record_type", "record_number",
                "status", "private_inspector", "registration_expired", "source_file", "source_row"])
    pcols = ["normalized_address", "registration_number", "start_date", "start_basis", "start_source", "end_date",
             "end_date_basis", "end_source", "end_status", "units", "rrio_events_attached"]
    write_table(conn, "rrio_registration_periods", periods, pcols)
    gcols = ["normalized_address", "registration_number_before_gap", "gap_start", "gap_start_source", "gap_end",
             "gap_end_source", "gap_status", "gap_days", "later_renewed", "units", "late_registration_violation_count",
             "late_registration_violation_records", "late_violation_same_regnum", "registration_expired_status_rows",
             "transfer_events_in_gap", "data_end_date"]
    write_table(conn, "rrio_gaps_all", gaps, gcols)
    write_table(conn, "rrio_coverage_unknown", unknown, ["normalized_address", "from_period_start", "until", "reason"])
    write_table(conn, "rrio_gaps_meta", [{"data_end_date": iso(data_end)}], ["data_end_date"])
    write_table(conn, "address_district",
                [{"normalized_address": k, "district": v, "district_source": dsrc[k]} for k, v in dist.items()],
                ["normalized_address", "district", "district_source"])
    write_table(conn, "lt_complaints", complaints, ["record_num", "normalized_address", "open_date", "record_type",
                "district", "is_complaint", "is_violation", "is_rent_increase", "source_file", "source_row"])
    ccols = ["normalized_address", "has_any_rrio_registration_on_file", "has_any_rrio_record_on_file",
             "evidence_kinds", "evidence_kind_count", "king_county_parcel_no_rrio", "lt_records_no_rrio_match",
             "lt_record_count", "reg03_complaints", "rrio_violations_no_registration", "note"]
    write_table(conn, "candidate_evidence", cands, ccols)

    fees = []
    if a.fee_schedule:
        with open(a.fee_schedule, encoding="utf-8") as fh:
            fj = json.load(fh)
        for s in fj["schedules"]:
            for k in ("effective_from", "property_fee", "additional_unit_fee", "late_fee", "term_days", "verified"):
                if k not in s:
                    raise SystemExit(f"fee schedule entry missing {k!r}: {s}")
            fees.append({**s, "schedule_label": s.get("label", "")})
            if not s["verified"]:
                log(f"WARNING fee schedule {s.get('label')!r} is marked NOT VERIFIED. F outputs carry that flag.")
    write_table(conn, "fee_schedule", fees, ["effective_from", "property_fee", "additional_unit_fee", "late_fee",
                                             "term_days", "verified", "schedule_label", "source"])
    conn.executescript(VIEWS_SQL)

    ev_count = 0
    if a.evictions:
        if not (a.evictions_address_col and a.evictions_date_col):
            raise SystemExit("--evictions needs --evictions-address-col and --evictions-date-col")
        cols = {"address": a.evictions_address_col, "date": a.evictions_date_col, "id": a.evictions_id_col}
        rows = load_by_named_columns(a.evictions, cols, "Evictions", a.allow_cp1252_fallback, log)
        ev = [{"filing_id": (r[a.evictions_id_col] if a.evictions_id_col else ""),
               "normalized_address": normalize_address(r[a.evictions_address_col]),
               "filing_date": iso(parse_date(r[a.evictions_date_col])),
               "source_file": os.path.basename(a.evictions), "source_row": i} for i, r in rows]
        write_table(conn, "evictions", ev, ["filing_id", "normalized_address", "filing_date", "source_file", "source_row"])
        conn.executescript(EVICTION_VIEW_SQL)
        ev_count = len(ev)
    conn.commit()

    outputs = ["rrio_registration_periods", "rrio_registration_gaps", "unregistered_candidates",
               "complaints_during_gaps", "rrio_coverage_unknown"]
    if fees:
        outputs.append("rrio_money_estimate")
    else:
        log("F skipped: no --fee-schedule given.")
    if ev_count:
        outputs.append("evictions_without_registration")
    else:
        log("D skipped: no eviction file given.")
    if fees:
        nofee = conn.execute("SELECT COUNT(*) FROM rrio_registration_gaps g WHERE NOT EXISTS "
                             "(SELECT 1 FROM fee_schedule f WHERE f.effective_from <= g.gap_start)").fetchone()[0]
        if nofee:
            log(f"WARNING {nofee} gaps start before the earliest fee schedule entry; they have no F row.")
    counts = {o: export(conn, o, a.out_dir) for o in outputs}
    for o, n in counts.items():
        log(f"OUTPUT {o}: {n} rows -> {o}_DRAFT.csv")
    if ev_count:
        for status, n in conn.execute("SELECT rrio_status_on_filing_date, COUNT(*) FROM evictions_without_registration GROUP BY 1 ORDER BY 2 DESC"):
            log(f"  D {status}: {n} filings")
    conn.close()

    manifest = {
        "status": "DRAFT, REVIEW REQUIRED - leads for review, not findings",
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "data_end": iso(data_end),
        "assumed_term_years": a.assumed_term_years,
        "rrio_files": [os.path.basename(f) for f in rrio_files],
        "snapshot_files": [os.path.basename(f) for f in snap_files],
        "complaints_file": a.complaints, "topics_file": a.topics, "reg03_file": a.reg03,
        "king_county_file": a.kc_file, "min_units": a.min_units, "evictions_file": a.evictions,
        "fee_schedule": a.fee_schedule, "row_counts": counts, "sqlite": sq,
        "rules": ["Nothing expiring on/after data_end is called lapsed.",
                  "Rows are not buildings; addresses are not parcels.",
                  UNMATCHED_NOTE,
                  "F is a calculation, not money owed.",
                  "Eviction wording: 'N filings at addresses with no RRIO registration on file on the filing date, "
                  "based on the records reviewed.' Never 'should not have been evicted.'"],
    }
    with open(os.path.join(a.out_dir, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    write_log(a.out_dir, log_lines)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HeaderError as e:
        print("STOPPED: " + str(e))
        sys.exit(2)
