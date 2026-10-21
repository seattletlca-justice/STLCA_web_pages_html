"""Recount every number on the STLCA citywide data page from the downloadable files.

Needs only Python 3 and the two files from the same page:
    landlord-tenant-records.csv      one row per landlord-tenant record from the City of Seattle open data portal
    elevator-addresses.csv           the elevator cross-reference (optional)

Run:   python recount.py                      (files in the same folder)
       python recount.py path\\to\\records.csv  path\\to\\elevator.csv
Nothing is downloaded and nothing is written. The script only counts."""
import csv, sys, os
from collections import Counter, defaultdict

here = os.path.dirname(os.path.abspath(__file__))
rec = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "landlord-tenant-records.csv")
ele = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "elevator-addresses.csv")
rows = list(csv.DictReader(open(rec, encoding="utf-8-sig", newline="")))
cp = [r for r in rows if r["record_type"] == "Complaint"]
nov = [r for r in rows if r["record_type"] == "Notice Of Violation"]

print("RECORDS")
print("  all landlord-tenant records:", f"{len(rows):,}")
for t, n in Counter(r["record_type"] for r in rows).most_common():
    print(f"    {t}: {n:,}")
print("  notices of violation are not subtracted from complaints; each type is counted on its own.\n")

print("BY YEAR OPENED   (no inspection date = the inspection date column is empty in the open data portal)")
print("  year  complaints  no_date  share_no_date  notices  notices_per_100_complaints")
for y in sorted({r["opened_year"] for r in cp}):
    c = [r for r in cp if r["opened_year"] == y]; v = [r for r in nov if r["opened_year"] == y]
    b = sum(1 for r in c if r["inspection_date_in_record"] == "no")
    print(f"  {y}  {len(c):10,}  {b:7,}  {100 * b / len(c):12.1f}%  {len(v):7,}  {100 * len(v) / len(c):10.1f}")
print(f"  all years: {len(cp):,} complaints, {len(nov):,} notices, {100 * len(nov) / len(cp):.1f} notices per 100 complaints\n")

print("BY COUNCIL DISTRICT")
print("  district  records  complaints  notices  notices_per_100  share_no_inspection_date  share_no_date_since_2018")
for d in sorted({r["district"] for r in rows if r["district"]}):
    rs = [r for r in rows if r["district"] == d]; c = [r for r in rs if r["record_type"] == "Complaint"]; v = [r for r in rs if r["record_type"] == "Notice Of Violation"]
    c18 = [r for r in c if int(r["opened_year"]) >= 2018]
    print(f"  {d:8}  {len(rs):7,}  {len(c):10,}  {len(v):7,}  {100 * len(v) / len(c):15.1f}  {100 * sum(1 for r in c if r['inspection_date_in_record'] == 'no') / len(c):23.1f}%  {100 * sum(1 for r in c18 if r['inspection_date_in_record'] == 'no') / len(c18):22.1f}%")
nod = [r for r in rows if not r["district"]]
print(f"  no district on record: {len(nod):,} records, {sum(1 for r in nod if r['record_type'] == 'Complaint'):,} complaints\n")

print("WHAT TENANTS REPORTED   (complaints that name each problem; one complaint can be in several groups)")
topics = [c for c in rows[0].keys() if c.startswith("topic_")]
print("  citywide, all", f"{len(cp):,}", "complaints:")
for t in topics:
    print(f"    {t[6:]:55} {sum(1 for r in cp if r[t] == 'yes'):7,}")
d7 = [r for r in cp if r["district"] == "7"]
print("  district 7,", f"{len(d7):,}", "complaints:")
for t in topics:
    print(f"    {t[6:]:55} {sum(1 for r in d7 if r[t] == 'yes'):7,}")

if os.path.exists(ele):
    E = list(csv.DictReader(open(ele, encoding="utf-8-sig", newline="")))
    print("\nELEVATOR CROSS-REFERENCE")
    print("  addresses:", len(E), "| rescue calls:", f"{sum(int(e['fire_department_rescue_calls']) for e in E):,}", "| elevator complaints:", sum(int(e["elevator_complaints"]) for e in E),
          "| addresses with no certified unit:", sum(1 for e in E if int(e["certified_units_on_file"]) == 0))
    byd = Counter(e["district"] or "none" for e in E)
    print("  by district:", ", ".join(f"{k}: {v}" for k, v in sorted(byd.items())))
