# 2026-11-11 P.I.E.R. Registration Lapses and Evictions

**Chat title to use:** `2026-11-11 P.I.E.R. Registration Lapses and Evictions`
**Written:** November 11, 2026, in the cloud chat "2026-11-11 Unregistered Apartments Since 2020" (https://claude.ai/code/session_01CmeqXMiAf9PakKmJHXYfz9)
**For:** the P.I.E.R. project (Property Intelligence & Enforcement Registry)
**Status:** DRAFT, REVIEW REQUIRED. This is a plan and instructions. Nothing in it has been run against P.I.E.R. yet.

Files that come with this note (same folder in the `STLCA_web_pages_html` repo):

- `docs/pier_handoff_2026-11-11/REG03_unregistered_or_lapsed_complaints_2020_2025_DRAFT.csv`: 159 complaints (2020–2025, 150 addresses) where the text says the rental is not registered, unregistered, not listed in RRIO, has an expired or lapsed registration, or is an unlicensed rental.
- `docs/pier_handoff_2026-11-11/topic-rules_REG-03.diff`: the proposed new issues-parser rule (section 7). Not placed yet. It is waiting for Kimberly's approval.

---

## 1. What Kimberly wants

1. A list of every rental property that is **unregistered**, or whose RRIO registration **lapsed**, with the dates:
   - when it was registered
   - when each registration ran out
   - whether it renewed later
   - how long each gap lasted
2. That list checked against **King County eviction records**, to count evictions filed at a property while no registration was on file.
3. How many buildings **have complaints and violations** but were unregistered or lapsed at the time. The same check for rent increases reported during those gaps.
4. **How much money is on the table** from RRIO: registration fees and late fees that the records suggest were never paid or charged.
5. The **RRIO history pulled for every property P.I.E.R. flags**, including the 21 district properties (section 8).
6. The results as a **new P.I.E.R. dashboard page**, added to the tab bar the other P.I.E.R. pages share (section 10), plus a standalone HTML report.

Kimberly's reason, in her words from this chat: tenants don't know their rights, the City has passed protections, but nothing is being enforced, and that has to change. Every output still follows the R.A.R.E. evidence rules in section 12. These are leads for review, not findings.

---

## 2. What to build

| # | Output | What it holds |
|---|---|---|
| A | `rrio_registration_periods` (table and CSV) | One row per registration period per address: address, registration number, start date, expiration date, the next period's start date, gap in days, units, and the source file and row for each date |
| B | `rrio_registration_gaps` (view) | Every gap that started on or after January 1, 2020: gap start, gap end (or "still open as of [data date]"), length, units, district |
| C | `unregistered_candidates` (view) | Addresses that look like rentals but have no RRIO record at any time, with the evidence for each (see 4.3) |
| D | `evictions_without_registration` (view) | Each eviction filing matched to the registration status on its filing date: covered, in a gap, never registered, or could not be matched |
| E | `complaints_during_gaps` (view) | Complaints, violations and rent-increase complaints opened while the address was in a gap |
| F | `rrio_money_estimate` (view) | Fee amounts calculated from the fee schedule and the gaps. Labeled as a calculation, not a record of money owed |
| G | A dashboard page and a standalone HTML report | KPI tiles, district breakdown, a searchable table, method and limits. Added to the shared P.I.E.R. tab bar |

---

## 3. Files P.I.E.R. needs, and where they are

| File | Where | Notes |
|---|---|---|
| RRIO yearly record exports, `RRIO_01012015_12212015_RecordList20251120.csv` through `RRIO_01012025_11202025_RecordList20251120.csv`, plus `RRIO 2015-1016.csv` | Kimberly's computer, `C:\Users\stlca\stlca_data\stlca-dashboard\CITY_MVP\polars\` (listed in the Drive "Traceability Document: Merging Seattle Rental Property Registration and RRIO Datasets") | 278,226 rows total per the June 18, 2026 cross-analysis. Column headers differ between years. The 2018 and 2023 files failed in an earlier merge because of column names, so check every file loads. Data ends **November 20, 2025**. Anything after that needs a new export from the Seattle Services Portal; only Kimberly can produce it. |
| Rental Property Registration snapshots (14 files, 2022–2026, e.g. `Rental_Property_Registration_20240611.csv`, `..._20260212_PORTAL_ACTIVE.csv`) | Same folder | `_20250506` and `_20250731` failed to load (bad bytes). `_20250908` gave 0 valid rows. Fix or note these; don't drop them silently. |
| `RRIO_PROPERTY_TIMELINE_CLEAN.csv` (81 MB) | Google Drive | Not opened in this chat. It may already hold part of output A. Open it and check its columns before rebuilding anything. |
| King County file with units, address and owners | Kimberly says it is on her computer | Name not known here. Search her folders by its columns (units, address, owner) before asking her. Use it for apartment unit counts and the never-registered check (4.3). |
| King County eviction records | **Not found.** Drive was searched for eviction and unlawful detainer files; none were there. | Ask Kimberly which eviction file she means. Each filing needs at least the property address and filing date. If she doesn't have one, it has to be obtained first (court records or a records request). Step D cannot start without it. |
| P.I.E.R. database (`stlca_property_intelligence.sqlite`) and `stlca_query.py` | Kimberly's computer | Already has `rrio_events`, `complaints_violations`, `permits_all` and the King County parcel/sales joins. |
| Landlord-tenant master, `MASTER_SOURCE_CITYWIDE_LLT_THRU_20251231_ENRICHED_01272026__PLUS_RECORDLIST-RARE.csv` | `STLCA_web_pages_html/input/` and Kimberly's computer | 56,258 records, 2003–2025. The locked source for property runs. |

---

## 4. Method

### 4.1 Registration periods (output A)

1. Load every RRIO record export into `rrio_events`, keeping the raw columns exactly as exported. Normalize addresses the P.I.E.R. way: capitals, single spaces, drop a trailing period, drop the trailing " SEATTLE" these exports add.
2. Registration and renewal events (`RENTAL PROPERTY REGISTRATION`, `RENTAL PROPERTY RENEWAL`) start or extend a period. Take expiration dates from the registration snapshots (`EXPIRESDATE`), matched on registration number.
3. A **gap** is the time between one period's expiration and the next registration or renewal at the same address. Record the days. A renewal filed after expiration closes the gap on its filed date.
4. **Only call a period lapsed if the data runs past its expiration date.** The newest RRIO data in hand ends November 20, 2025. A registration that expires after that date is "unknown," not "lapsed." Section 5.1 shows why this matters.
5. Keep `TRANSFER EXISTING REGISTRATION TO NEW OWNERS` events. A sale can look like a gap when it isn't one.
6. Keep `RENTAL PROPERTY LATE REGISTRATION VIOLATION` events and registration-expired status rows next to each gap. They are the City's own record that it noticed. Per the June 18 cross-analysis there are 48,312 late-registration violation rows and 14,046 registration-expired status rows (all years, rows not buildings).
7. Keep apartments only for the main counts. Use unit counts from the snapshots, and from the King County file when the snapshot has none. Kimberly chooses the cutoff; ask her. Five or more units is one option.

### 4.2 Gaps since 2020 (output B)

From A, take every gap that starts on or after January 1, 2020. For each gap, record:

- start and end dates
- days unregistered
- units and district
- whether the address later renewed
- whether a Late Registration Violation exists for that registration number

### 4.3 Never registered (output C)

None of these proves a building had to register. Each is a lead.

1. **King County parcels used as apartments** inside Seattle, with no RRIO record at any time. These are the strongest leads.
2. **Landlord-tenant complaint addresses with no RRIO match.** The June 18 cross-analysis matched 10,296 of 20,331 such addresses. Most of the other 10,035 will turn out to be spelling differences, owner-occupied homes or exempt housing. Check before counting.
3. **Complaints saying the rental is not registered.** See the 159-row CSV that comes with this note, produced by the proposed REG-03 rule (section 7). Several name a registration number or a lapse date, for example:
   - 002265-22CP: "rental registration lapsed in August 2021"
   - 013227-23CP: "expired registration as of 5/18/2021, record number 001-0120650"
4. **RRIO violation records** at addresses with no registration on file.

### 4.4 Evictions (output D)

For each eviction filing, look up the address's registration status on the filing date:

- **covered**: a registration period was in force
- **in a gap**: the registration had lapsed
- **never registered**
- **could not match**: address problem

Count each group. Also report how many filings fall in apartment buildings above the unit cutoff.

Before any statement about whether an eviction was allowed, read section 6.

### 4.5 Complaints, violations and rent increases during gaps (output E)

Join `complaints_violations` and the landlord-tenant master to the gaps by address and open date. Report:

- complaints opened during a gap
- violations (notices of violation, citations) opened during a gap
- rent-increase complaints opened during a gap (parser categories `RENT_INCREASE_FEES`, rules RENT-01 and RENT-05)

### 4.6 Money (output F)

Show calculations, never claims. Keep them separate from LedgerHawk's enforcement-money measures.

1. **Registration fees not paid during gaps** = for each gap, the fee for the units it covers. SDCI fee documents found in this chat's search list:
   - $110 per property for two years, which includes the first unit
   - $20 for each additional unit
   - a late registration or renewal fee of $31.50 (form updated 1/2024)

   These amounts must be checked against the current SDCI fee schedule before use. Older documents show different amounts.
2. **Late fees**: count the late-registration events. The data doesn't show whether a fee was charged or paid, so label this as "late fees the schedule would apply," not money owed.
3. **Penalties**: don't estimate them until the penalty section of SMC 22.214 has been read and quoted.
4. **Don't reuse the "hundreds of millions to over a billion dollars" figure** from the older Drive document. It assumed 180 days of lapse at $500 a day for every property; it is not a record.

### 4.7 RRIO history for flagged properties

For each property on the final lists, and for each of the 21 district properties once Kimberly confirms them, run `python stlca_query.py --address "ADDRESS"`. That prints the property's full RRIO event history. Save each one beside the property's other evidence.

---

## 5. Things already found that change the plan

### 5.1 The Rental Housing Inventory "Lapsed registration" filter is not reliable

The Rental Housing Inventory page (https://claude.ai/artifact/UvMtAoRMkWT6XQ2HGinwdp) marks 8,648 of 28,301 registrations as lapsed. That count can't be used:

- Its data comes from a registration list taken in November 2025. The newest registered date in it is 2025-11-18, and the newest RRIO event is 2025-11-20.
- The page calls a registration "lapsed" when its expiration date is before September 12, 2026. Every one of the 8,648 expires between November 2025 and September 2026, after the list was taken. The list can't show whether those properties renewed.
- The City's list also drops registrations once they expire; the earliest expiration date in it is 2025-11-18. So registrations that lapsed before November 2025 aren't on it at all.

**Fix:** rebuild "lapsed" from the yearly record exports plus the dated snapshots (4.1). Update the inventory page's filter and wording to match. Until then, label that filter as not checked.

### 5.2 The RRIO status field does not show lapses

The raw status field reads "Active Registration" on all 28,301 rows of that same list, expired or not. Never use it alone to show a property is registered.

### 5.3 Two claims in the older Drive document should not be reused

The "Traceability Document: Merging Seattle Rental Property Registration and RRIO Datasets" makes two claims:

- **It says late-registration violations are rare compared with expirations.** The June 18, 2026 cross-analysis counts more late-registration violation rows (48,312) than expired-status rows (14,046), which points the other way.
- **Its penalty figure is a model**, not a record (see 4.6).

### 5.4 Address joins err both ways

One address can hold several buildings, and one building can have several addresses (1102 and 1110 8th Ave). Spelling differences make a match fail. A failed match is not proof a property is unregistered.

---

## 6. Legal points to check before saying anything about evictions

SDCI's Just Cause Eviction page says that to end or not renew a tenancy, a landlord must state one of the approved reasons **and be in compliance with the Rental Registration & Inspection Ordinance**: https://seattle.gov/construction-and-inspections/codes/codes-we-enforce-(a-z)/just-cause-eviction-ordinance

The exact wording of SMC 22.206.160 was **not** read in this chat. Before publishing anything about evictions:

1. Pull the current text of SMC 22.206.160 and SMC 22.214, and quote the registration language and any exceptions.
2. Check which housing is exempt from RRIO, and check each property against those exemptions.
3. Match at the unit level where possible. A building registration may not cover every unit.
4. Use record-bounded wording, for example: "N eviction filings were made at addresses with no RRIO registration on file on the filing date, based on the records reviewed." Do **not** say tenants "should not have been evicted." That is a legal conclusion the records alone can't support.

Run the wording through `stlca-verify`, then `stlca-redteam`, before anything goes public.

---

## 7. Issues parser: proposed new rule REG-03 (waiting for approval)

Kimberly asked for these keywords to be added to the issues parser. The copy reviewed is `STLCA_web_pages_html/site/STLCA_HOSTINGER_UPLOAD/topic-rules.py` (SHA-256 `9625ef84…f7ca3920`), which calls itself `llt_issue_rules.py`. **It is not yet confirmed that this matches the copy on Kimberly's computer.** Hash her copy before applying the change.

**What REG-03 does.** It is a new rule in the existing category "Rental registration paperwork" (`REGISTRATION_PAPERWORK`). No category is added or renamed. It catches:

- "not / never / not yet / not currently / not properly / without being registered", including "isn't" and "hasn't" forms
- "nor is the property registered"
- "unregistered"
- "not listed in / on / with RRIO" and "not listed on the rental housing registrations map"
- "registration expired / lapsed" and "expired / lapsed registration"
- "unlicensed rental / unit / apartment", "while it was unlicensed", "not licensed (or inspected) to be a rental"

It skips mentions about contractors, tree service providers, vehicles, pets, elevators, short-term rentals and registered mail.

It runs just before REG-01, so these statements get their own rule ID in `match_audit.csv`. That lets P.I.E.R. pull them out as a list.

**Tested in this chat**, against all 40,540 complaint records in the landlord-tenant master (`input/` copy, which is all capital letters):

- Self-test: 145 of 145 rules pass, including REG-03.
- "Rental registration paperwork" count: 386 → 415 records (+29). **No other category changed.**
- REG-03 marks 199 complaint records, 159 of them from 2020–2025 (the CSV that comes with this note).
- Some statements REG-01 already counted, such as "not registered" and "unregistered," now carry REG-03 instead. Totals are unchanged, but REG-01's rule count drops by the same amount.

**Known limits:**

- One record (007530-22CP, "I don't even think she is a registered rental property") is still missed.
- REG-01's existing matches on "unregistered" and "not registered" still count a few non-rental mentions (tree services, contractors, dogs, vehicles). This rule doesn't change that.
- The REG-03 example is taken from the all-capitals master CSV. The approved JSON the parser normally reads may have different capitalization. The self-test ignores case, so it still passes.

**Downstream effects if it is placed:**

- The website pages that link `topic-rules.py` as "Show our work":
  - `data.html`
  - `district-7-dashboard.html`
  - `district-7-dossier.html`
  - `how-we-counted.html`
- The eight map pages that embed registration category counts.

Those pages show numbers from the last run. If the script changes without a re-run, the published script won't reproduce the published numbers. **Place the rule only together with a re-run on `LLT_APPROVED_THROUGH_20251231.json` and a rebuild of `landlord-tenant-records.csv` and those pages.**

The exact change is in `docs/pier_handoff_2026-11-11/topic-rules_REG-03.diff`. It applies cleanly to the repo copy (`patch --dry-run` passed).

---

## 8. The 21 district properties and their run code

**The list of 21 addresses was not found.** Places checked:

- this chat
- the `STLCA_web_pages_html` and `seattle-r.a.r.e.-pipeline` repos
- Google Drive (searched for "21 addresses", "21 properties", "per district" and the run script name)
- the November 10 evening briefing

Other Claude sessions on Kimberly's computer could not be opened from the cloud. No run code for 21 addresses was given in this chat.

The Drive "STLCA District Dashboards and Dossiers" plan asks each dossier to feature "two or three properties that teach something different." Three per district is 21. **Ask Kimberly to confirm the 21 addresses before running anything.**

Run code, once the list is confirmed. This is a template that calls the existing `RUN_RARE_PROPERTY.ps1` one property at a time. It was **not** syntax-checked; there is no PowerShell in the cloud session. Run it from the pipeline folder on Kimberly's computer. Every run needs her approval (pipeline `AGENTS.md`).

```powershell
# RUN_DISTRICT_PROPERTIES.ps1 -- template. Fill in one line per property, then run from the pipeline folder.
# InputFolder is the property's batch folder, e.g. inputs\RARE_DISTRICT_PROPERTY_BATCHES_20251231\D2\00029__101_6TH_AVE_S__eea7bc4d
$list = @(
    # @{ Property = "101_6TH_AVE_S"; District = "D2"; InputFolder = "inputs\RARE_DISTRICT_PROPERTY_BATCHES_20251231\D2\00029__101_6TH_AVE_S__eea7bc4d" }
)
foreach ($p in $list) {
    Write-Host "=== $($p.Property)  $($p.District) ==="
    & .\RUN_RARE_PROPERTY.ps1 -Property $p.Property -District $p.District -InputFolder $p.InputFolder -Workers 1 -MinRequestInterval 2.0
    Write-Host "Finished $($p.Property) with exit code $LASTEXITCODE. Open README_RUN.txt in its run folder."
}
```

Runs already known (from the website README, September 14, 2026):

| Property | District | Run status then |
|---|---|---|
| 8201 Aurora Ave N | D6 | QA pass |
| 101 6th Ave S | D2 | QA pass |
| 1102 8th Ave | D7 | Still capturing |
| 308 4th Ave S | D2 | Still capturing |

Check their output folders before re-running any of them.

---

## 9. Problem found in the GitHub copy of `RUN_RARE_PROPERTY.ps1`

In `seattle-r.a.r.e.-pipeline` (commit `74c29f8`, September 8, 2026), the "ENGINE PREFLIGHT" block sits **after** the script's final closing brace (after line 359). Its comment says it should run before any web requests. As written, it runs after the whole run has finished, outside the error handling.

The copy on Kimberly's computer may be different. Check it before the next run. Don't change it without her approval; this note only reports it.

---

## 10. The P.I.E.R. pages with the tab bar

Kimberly could not find this page. The P.I.E.R. pages share a tab bar across the top that links them all:

- P.I.E.R. Registry: https://claude.ai/artifact/XzJJhUzF46C98V5J9cRZZQ
- Rental Housing Inventory: https://claude.ai/artifact/UvMtAoRMkWT6XQ2HGinwdp
- P.I.E.R. Dashboard (gallery name "STLCA Property Intelligence"): https://claude.ai/artifact/3HuQe1k7UEkfbZL7eSuB3v

The tab bar also links the Elevator & Fire-Rescue Cross-Reference and the Everspring Inn and Lowell Emerson case studies. Add the new page from output G to this tab bar on every page that has it.

---

## 11. Questions for Kimberly

1. Which 21 addresses (section 8)?
2. Which file is the King County eviction data, or does it still need to be obtained?
3. What is the name of the King County file with units, address and owners?
4. What unit count makes a building an "apartment" for the main counts?
5. Do you approve placing parser rule REG-03, with a re-run of the parser and rebuilt website counts (section 7)?
6. Can you export new RRIO RecordList data from the Seattle Services Portal for November 20, 2025 to today? Without it, nothing after November 20, 2025 can be called lapsed.

---

## 12. Rules that apply to everything in this note

- Every number names its source file, date range and record universe.
- Rows are not buildings. Say which one each number counts.
- A missing record is not proof something didn't happen. A failed address match is not proof a property is unregistered.
- Flags are leads for review, not findings and not guilt scores.
- Calculated money is labeled as a calculation.
- Nothing is published until it passes `stlca-verify`, then `stlca-redteam`.
