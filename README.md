# STLCA website

**Seattle Tenant-Landlord Compliance & Accountability** · powered by Seattle R.A.R.E.
(Records Accountability Review Engine)

This is the one home for the website. Everything else is reference.

```
site/          THE WEBSITE. The only thing that gets published.
drafts/        Pages being built. Not linked from the site yet.
  case-studies/   8201 Aurora Ave N (narrative + evidence ledger) — DRAFT, not yet redteamed
  templates/      the three Figma "investigation" pages the case-study ledger is built from
docs/          Transfer docs and working notes
_INBOX/        Drop anything new here. It gets sorted from here.
_REFERENCE/    Old builds, the bundled R.A.R.E. site, brand assets. Kept, not edited. Not in git.
input/         Large citywide extracts. Not in git (except the one LT master already committed).
```

## Open the site

Double-click `OPEN STLCA SITE.bat` on the Desktop, or open `site/index.html`.
No server needed.

## Rebuild after changing data

```bash
cd site
python build.py   # regenerates assets/data.js and the district pages from site/data/*.json
python qa.py      # pre-publication checks
```

`build.py` reads the Addison source CSV from the SOURCE_RECORDS evidence tree, which is not in
this repo. It looks on the OneDrive Desktop by default; set `STLCA_SOURCE_ROOT` to point elsewhere.

## How a page moves from draft to site

1. Built in `drafts/` from a QA-passed R.A.R.E. run, verified against primary sources.
2. Redteamed (`stlca-redteam`).
3. Moved into `site/`, linked from its section index, passes `qa.py`.

## Rules that apply to every page

- Every number traces to a named record or data file.
- A limitation stays attached to the claim it limits.
- **Public record, public name.** A person is named when the name appears in a public record,
  attached to that record.
- Missing data is not proof of non-occurrence.

## Case-study pipeline status (2026-09-14)

| Property | District | R.A.R.E. run | Page |
|---|---|---|---|
| 8201 Aurora Ave N (Everspring) | D6 | `D6_8201 AURORA AVE N_20260914_073553` — QA pass | draft, not redteamed |
| 101 6th Ave S | D2 | `D2_101_6TH_AVE_S_054004_RECOVERY_20260912_135548` — QA pass | not started |
| 1102/1110 8th Ave (Lowell Emerson) | D7 | `D7_1102 8TH AVE_20260914_152205` — still capturing | waiting on run |
| 308 4th Ave S (The Addison) | D2 | `D2_308 4TH AVE S_20260914_152207` — still capturing | waiting on run |

Goal: one case study per district, seven total.
