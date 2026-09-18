#!/usr/bin/env python3
"""
STLCA site build.

Reads the authoritative data layer in data/ and emits assets/data.js, which is the
single object every page renders from. No figure is typed into page markup.

The Addison case extract is computed here from its source CSV rather than transcribed,
so the case-study page inherits the same reproducibility rule as the rest of the site.

Binding test (build instructions section 11): change a value in
data/District_3_SUMMARY.json, run this script, reload district-3.html, and the page
reflects the change with no HTML edit.

Usage:  python build.py
"""
import csv
import hashlib
import json
import os
import re
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ASSETS = os.path.join(HERE, "assets")
REPO = os.path.dirname(HERE)

# Source records are not kept in this repo (too large for git). Resolution order:
# STLCA_SOURCE_ROOT env var, then a SOURCE_RECORDS folder beside this site, then the
# OneDrive evidence tree where they were organized on 2026-09-08.
_SOURCE_CANDIDATES = [
    os.environ.get("STLCA_SOURCE_ROOT", ""),
    os.path.join(REPO, "SOURCE_RECORDS"),
    os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "STLCA SITE",
                 "STLCA_Extraction_Program_Creation", "01_APPROVED_CANDIDATE_PIPELINE_VERIFIED",
                 "STLCA_web_pages_html", "SOURCE_RECORDS"),
]
SOURCE_ROOT = next((p for p in _SOURCE_CANDIDATES if p and os.path.isdir(p)), None)
if SOURCE_ROOT is None:
    raise SystemExit("SOURCE_RECORDS not found. Set STLCA_SOURCE_ROOT to its folder.")

ADDISON_CSV = os.path.join(
    SOURCE_ROOT, "case_addison", "Data and Analysis",
    "ADDISON Code_Complaints_and_Violations_20250509.csv")
LT_MASTER = os.path.join(
    SOURCE_ROOT, "master_extracts",
    "case_nov_MASTER_SOURCE_CITYWIDE_LLT_THRU_20251231_ENRICHED_01272026__PLUS_RECORDLIST-RARE.csv")

DISTRICT_NAMES = {
    "1": "West Seattle / Delridge",
    "2": "Southeast Seattle / Beacon Hill",
    "3": "Central Seattle / Capitol Hill",
    "4": "Northeast Seattle / University",
    "5": "North Seattle / Lake City",
    "6": "Northwest Seattle / Ballard",
    "7": "Downtown / Queen Anne / Magnolia",
}

POINT_RE = re.compile(r"^\s*POINT\s*\(", re.I)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_addison():
    """Compute the Addison on 4th extract from the May 2025 portal export."""
    with open(ADDISON_CSV, encoding="utf-8-sig", errors="replace") as fh:
        rows = list(csv.DictReader(fh))

    # The export carries one row for an unrelated address; the case universe is the
    # 308 4th Ave S parcel only.
    onsite = [r for r in rows
              if r["OriginalAddress1"].strip().upper().replace("4TH", "4TH") == "308 4TH AVE S"]
    offsite = len(rows) - len(onsite)

    by_type, by_status, by_year = {}, {}, {}
    geom_in_inspdate = blank_inspdate = blank_inspresult = 0

    for r in onsite:
        by_type[r["RecordType"].strip()] = by_type.get(r["RecordType"].strip(), 0) + 1
        st = r["StatusCurrent"].strip().upper()
        by_status[st] = by_status.get(st, 0) + 1
        yr = r["OpenDate"][:4] if r["OpenDate"] else "unknown"
        by_year[yr] = by_year.get(yr, 0) + 1

        lid = r["LastInspDate"].strip()
        if POINT_RE.match(lid):
            geom_in_inspdate += 1
        elif not lid:
            blank_inspdate += 1
        if not r["LastInspResult"].strip():
            blank_inspresult += 1

    n = len(onsite)
    usable_dates = n - geom_in_inspdate - blank_inspdate

    return {
        "id": "addison-on-4th",
        "title": "The Addison on 4th",
        "address": "308 4th Ave S, Seattle",
        "source": {
            "file": os.path.basename(ADDISON_CSV),
            "sha256": sha256(ADDISON_CSV),
            "export_date": "2025-05-09",
            "location": "SOURCE_RECORDS/case_addison/Data and Analysis/",
        },
        "totals": {
            "records_at_address": n,
            "rows_in_export": len(rows),
            "rows_excluded_other_address": offsite,
            "unique_years": len([y for y in by_year if y != "unknown"]),
        },
        "by_record_type": by_type,
        "by_status": by_status,
        "by_year": dict(sorted(by_year.items())),
        "field_integrity": {
            "lastinspdate_containing_geometry": geom_in_inspdate,
            "lastinspdate_blank": blank_inspdate,
            "lastinspdate_usable_dates": usable_dates,
            "lastinspdate_geometry_pct": round(geom_in_inspdate / n * 100, 1) if n else 0,
            "lastinspresult_blank": blank_inspresult,
            "lastinspresult_blank_pct": round(blank_inspresult / n * 100, 1) if n else 0,
        },
        "supports": "That in this export the LastInspDate field carried geographic point "
                    "geometry rather than inspection dates, at building level, across the "
                    "full record history for this address.",
        "does_not_support": "That no inspection of this building ever occurred, or that any "
                            "specific condition went unaddressed.",
    }


SOURCE_GROUPS = {
    "master_extracts": ("Master extracts",
                        "The frozen analytic CSVs every figure derives from."),
    "annual_recordlists": ("Annual record lists",
                           "SDCI Code Complaints and Violations exports, one file per year, 2003–2025."),
    "rrio": ("RRIO / Ordinance 125054",
             "Rental registration extract, located RRIO annual reports, and the landlord-tenant "
             "parser with its QA report and narrative-review queue."),
    "lastinspdate": ("LastInspDate evidence",
                     "Portal exports from before and after the July 2025 change, the published "
                     "finding report, and related agency correspondence."),
    "case_addison": ("Addison on 4th",
                     "Complaint and violation record, analysis working files, and inspection exhibits "
                     "for the case study."),
    "pra_and_correspondence": ("Records requests & correspondence",
                               "Public Records Act requests to SDCI and ITD, agency replies, and the "
                               "CB 121254 legislative source."),
    "reference_reports": ("Reference documents",
                          "Prior reports, third-party source documents, editorial standards, and "
                          "earlier KPI summaries."),
}


def scan_source_records():
    """Inventory SOURCE_RECORDS so the reports page lists what actually exists."""
    base = SOURCE_ROOT
    groups = []
    for key, (title, desc) in SOURCE_GROUPS.items():
        d = os.path.join(base, key)
        if not os.path.isdir(d):
            continue
        files, total = [], 0
        for root, _, names in os.walk(d):
            for n in names:
                p = os.path.join(root, n)
                sz = os.path.getsize(p)
                total += sz
                files.append({"name": n,
                              "rel": os.path.relpath(p, base).replace("\\", "/"),
                              "bytes": sz})
        files.sort(key=lambda x: -x["bytes"])
        groups.append({"key": key, "title": title, "description": desc,
                       "count": len(files), "bytes": total,
                       "files": files[:14], "truncated": max(0, len(files) - 14)})
    return groups


def load_layer():
    """Load every authoritative JSON in data/ into one bound object."""
    districts = {}
    for i in range(1, 8):
        with open(os.path.join(DATA, f"District_{i}_SUMMARY.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        d["name"] = DISTRICT_NAMES[str(i)]
        districts[str(i)] = d

    with open(os.path.join(DATA, "citywide_enforcement_gap.json"), encoding="utf-8") as fh:
        gap = json.load(fh)
    with open(os.path.join(DATA, "findings.json"), encoding="utf-8") as fh:
        findings = json.load(fh)

    # Provenance gate: every district must declare the same verified source.
    expected = findings["source"]["sha256"]
    bad = [i for i, d in districts.items() if d["source"]["sha256"] != expected]
    if bad:
        raise SystemExit(f"PROVENANCE FAILURE: districts {bad} declare a different source sha256")

    # Reconciliation gate: district record counts must sum to the published assigned total.
    total = sum(d["totals"]["record_count"] for d in districts.values())
    if total != findings["universe"]["assigned_to_district"]:
        raise SystemExit(
            f"RECONCILIATION FAILURE: districts sum to {total:,}, "
            f"universe declares {findings['universe']['assigned_to_district']:,}")

    # The retired 40,062-row universe must not appear as any district figure.
    retired = {u["count"] for u in findings["coexisting_universes"] if "Retired" in u["permitted_use"]}
    for i, d in districts.items():
        if d["totals"]["record_count"] in retired:
            raise SystemExit(f"RETIRED UNIVERSE FAILURE: district {i} uses a retired denominator")

    return districts, gap, findings, total


def build_search_index(districts, gap, findings, addison):
    """Flat, self-contained index so every page and figure is findable."""
    idx = []

    def add(title, kind, url, text, tags):
        idx.append({"title": title, "kind": kind, "url": url,
                    "text": " ".join(str(t) for t in text), "tags": tags})

    add("The Record", "Page", "index.html",
        ["editorial front door accountability question Seattle housing enforcement CB 121254",
         "records review accountability"], ["overview"])
    add("Findings", "Page", "findings/index.html",
        ["three fixed core findings evidence establishes does not establish"], ["findings"])

    for f in findings["findings"]:
        add(f"Finding {f['number']} — {f['title']}", "Finding",
            f"findings/{f['id']}.html",
            [f["statement"], f["supports"], f["does_not_support"], f["critical_limitation"]],
            ["findings", f"finding-{f['number']}"])

    fs = findings["feature_story"]
    add(f"Feature — {fs['title']}", "Feature", "findings/rrio-loop.html",
        [fs["scope"], fs["purpose"], fs["caution"],
         fs["matched_complaints"], "RRIO certification mold pests plumbing electrical heat"],
        ["findings", "rrio"])

    add("Districts", "Page", "districts/index.html",
        ["district index routing map seven council districts"], ["districts"])

    for i, d in districts.items():
        t, ic, sc = d["totals"], d["inspection_completeness"], d["substantive_complaint_classification"]
        add(f"District {i} — {d['name']}", "District", f"districts/district-{i}.html",
            [d["name"], t["record_count"], t["unique_addresses"], t["cp_count"], t["vi_count"],
             ic["no_lastinspdate"], ic["no_lastinspdate_pct"], sc["substantive_complaints"],
             "dossier record count inspection completeness substantive complaints"],
            ["districts", f"d{i}"])

    add("Citywide KPI", "Dashboard", "dashboards/citywide-kpi.html",
        ["landlord tenant universe 56258 inspection completeness closure documentation"],
        ["dashboards"])
    add("NOV-to-Complaint Record Ratio", "Dashboard", "dashboards/enforcement-gap.html",
        ["record ratio by year 2003 2025 VI CP composition not conversion",
         gap["pre_2018_baseline_2011_2016_avg_pct"], gap["post_2018_2022_2025_avg_pct"]],
        ["dashboards", "charts"])
    add("Inspection Completeness by District", "Dashboard", "dashboards/inspection-completeness.html",
        ["blank LastInspDate share by district comparison chart"], ["dashboards", "charts"])

    add("Case Studies", "Page", "case-studies/index.html", ["building level case studies"], ["cases"])
    add(f"Case Study — {addison['title']}", "Case study", "case-studies/addison-on-4th.html",
        [addison["address"], addison["supports"], addison["does_not_support"],
         "LastInspDate geometry POINT field integrity building level"], ["cases"])

    add("Methodology", "Page", "methodology.html",
        ["record universe provenance QA denominators limitations claim ceiling",
         "collect verify trace report"], ["methodology"])
    add("Reports & Source Records", "Page", "reports/index.html",
        ["source records public records act RRIO annual recordlists master extracts"], ["reports"])
    add("About", "Page", "about.html",
        ["STLCA Seattle RARE records accountability review engine not an authority"], ["about"])
    return idx


DISTRICT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>District {n} — STLCA</title>
<meta name="description" content="District {n} ({name}): landlord-tenant record counts, inspection completeness, closure documentation and reported conditions, drawn from District_{n}_SUMMARY.json.">
<link rel="stylesheet" href="../assets/stlca.css">
</head>
<body class="screen" data-page="districts/index.html" data-district="{n}">

<main class="wrap">
  <div class="crumb"><a href="../index.html">The Record</a> → <a href="index.html">Districts</a> → <span id="crumb-d"></span></div>

  <div class="page-head">
    <div class="eyebrow" id="eyebrow"></div>
    <h1 id="title"></h1>
    <h2 id="subtitle" style="margin-top:-6px;font-weight:500;color:var(--screen-ink-2)"></h2>
    <p class="lede" id="lede"></p>
    <div id="siblings" style="margin-top:14px"></div>
  </div>

  <section class="grid g4" id="tiles"></section>

  <h2>What kind of records these are</h2>
  <div id="mix"></div>
  <div class="notice" id="comp-note"></div>
  <div id="comp"></div>

  <h2>Complaints and violations over time</h2>
  <div id="cpvi"></div>
  <div id="ratio"></div>

  <h2>What tenants reported</h2>
  <div id="habit"></div>
  <h3>Strongest classification signals</h3>
  <div class="scroll-x"><table class="data" id="signals">
    <thead><tr><th>Signal</th><th>Source</th><th>Records</th></tr></thead><tbody></tbody>
  </table></div>

  <h2>How long records stayed open</h2>
  <section class="grid g3" id="rt-tiles"></section>
  <div id="rt-dist"></div>
  <div class="limitation" id="rt-anomaly"></div>

  <h2>Limitations</h2>
  <div class="limitation">
    <b>Inspection-date limitation — reproduced verbatim</b>
    <span id="verbatim"></span>
  </div>

  <div class="prov" id="prov"></div>
</main>

<script src="../assets/data.js"></script>
<script src="../assets/stlca.js"></script>
<script src="../assets/district-page.js"></script>
</body>
</html>
"""


def write_district_pages(districts):
    """One template, seven shells. Only data-district differs."""
    out = os.path.join(HERE, "districts")
    os.makedirs(out, exist_ok=True)
    for i, d in districts.items():
        html = DISTRICT_TEMPLATE.format(n=i, name=d["name"])
        with open(os.path.join(out, f"district-{i}.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
    return len(districts)


def main():
    districts, gap, findings, assigned = load_layer()
    addison = build_addison()

    bundle = {
        "generated": date.today().isoformat(),
        "findings": findings,
        "districts": districts,
        "district_names": DISTRICT_NAMES,
        "citywide_enforcement_gap": gap,
        "addison": addison,
        "source_records": scan_source_records(),
        "reconciliation": {
            "districts_sum": assigned,
            "universe_assigned": findings["universe"]["assigned_to_district"],
            "unassigned": findings["universe"]["unassigned"],
            "universe_total": findings["universe"]["records"],
            "status": "RECONCILED",
        },
    }
    bundle["search"] = build_search_index(districts, gap, findings, addison)

    os.makedirs(ASSETS, exist_ok=True)
    out = os.path.join(ASSETS, "data.js")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("/* GENERATED by build.py — do not edit. Edit data/*.json and rebuild. */\n")
        fh.write("window.STLCA_DATA = ")
        json.dump(bundle, fh, indent=1, ensure_ascii=False)
        fh.write(";\n")

    with open(os.path.join(DATA, "addison_case.json"), "w", encoding="utf-8") as fh:
        json.dump(addison, fh, indent=2, ensure_ascii=False)

    n_pages = write_district_pages(districts)

    print(f"data.js written  ({os.path.getsize(out):,} bytes)")
    print(f"  district pages {n_pages} generated from one template")
    print(f"  districts      {len(districts)}  reconciled to {assigned:,} assigned records")
    print(f"  findings       {len(findings['findings'])} fixed + 1 feature story")
    print(f"  addison        {addison['totals']['records_at_address']} records at "
          f"{addison['address']}")
    print(f"  search index   {len(bundle['search'])} entries")
    print(f"  LT master sha  {findings['source']['sha256'][:16]}… verified against districts")


if __name__ == "__main__":
    main()
