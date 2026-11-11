# 2026-11-11 P.I.E.R. Registration Lapses and Evictions: law, fees and build code

**Status:** DRAFT, REVIEW REQUIRED. Not yet checked with `stlca-verify`. Nothing here is a finding.
**Written:** November 11, 2026, cloud chat "2026-11-11 P.I.E.R. Registration Lapses and Evictions".
**Standalone page:** `law-fees-and-code-2026-11-11.html` (same folder).

---

## 1. The law (steps 1 of the transfer note)

### 1.1 What could and could not be opened

| Source | Result |
|---|---|
| Seattle Municipal Code on Municode (`library.municode.com`), SMC 22.206.160 and Chapter 22.214 | **Could not be read.** At first the network blocked it. After the session was allowed to reach it, the site answered "Access blocked. Your browser version can't access this site" (HTTP 403) to both a plain request and a real headless browser. The site refuses automated readers. I did not try to get around that. |
| Seattle City Clerk code pages (`clerk.seattle.gov/~public/toc/22-214.htm`, `22-206.htm`) | **Could not be read.** The page returned a bot-check page, not the code. |
| SDCI "Just Cause Eviction Ordinance" web page (seattle.gov) | **Opened.** Quoted below. No "last updated" date is shown on the page. |
| SDCI "RRIO Registration Exceptions" PDF | **Opened.** PDF dated September 2025 (created 2025-09-11, modified 2025-09-24). Quoted below. |
| SDCI "RRIO Penalties and Violations" PDF | **Opened.** PDF created 2025-11-25, modified 2026-01-06. Quoted below. |
| SDCI "RRIO Program Fees" PDF | **Opened.** PDF created 2025-11-25, modified 2026-01-06. Quoted in section 2. |

**So the exact wording of the code itself is still not in hand.** What follows is SDCI's own published description of the law, quoted word for word. That is an official City source, but it is a summary, not the code. Before anything about evictions is published, Kimberly needs the code text (open the Municode links in her own browser and save the pages, or ask SDCI).

### 1.2 Just cause and registration: what SDCI's page says

From the SDCI page "Just Cause Eviction Ordinance" (https://www.seattle.gov/sdci/codes/codes-we-enforce-(a-z)/just-cause-eviction-ordinance), read 2026-11-11:

> "The Just Cause Eviction Ordinance applies to month-to-month renters, renters with verbal agreements, and renters with expiring term leases. To end or not offer to renew one of these agreements, a landlord or property manager must state one of the 16 approved reasons listed in the Just Cause Eviction Ordinance and be in compliance with the Rental Registration & Inspection Ordinance."

**Important for the plan: the section number may have changed.** The transfer note cites SMC 22.206.160. The same SDCI page links the Just Cause Eviction Ordinance to Municode node `CH22.205JUCAEV` (Chapter 22.205, "Just Cause Eviction"), and cites "SMC 22.205.010.P" for criminal-activity notices. Some older complaint records cite "SMC 22.206.160(C)". This points to the just cause rules now sitting in SMC Chapter 22.205. **Not confirmed** until the code text is read. Use "the Just Cause Eviction Ordinance" in any wording until the right section is confirmed.

**Exceptions:** the code's exact registration language and any exceptions (for example, timing of registration relative to a notice) were **not** read. A web search summary pointed to an old council bill with the words "Regardless of whether just cause for eviction may exist, an owner may not evict a residential tenant from a rental housing unit if the unit is not registered…", but that bill is listed as retired and the text was not opened. **Do not quote it.**

### 1.3 Who must register, and who is exempt (Chapter 22.214)

From the SDCI PDF "RRIO Registration Exceptions" (https://www.seattle.gov/documents/Departments/SDCI/Codes/RRIO/RRIORegistrationExceptions.pdf):

> "The following types of properties or rentals do not need to register with the Rental Registration and Inspection Ordinance (RRIO) program (subsection 22.214.030A of the ordinance):
> 1. Housing units lawfully used as short-term rentals, if the housing unit is the primary residence of the short-term rental operator
> 2. Housing units rented for less than 12 consecutive months because the property owner, who previously occupied the unit as a primary residence, takes a work-related leave of absence or assignment that temporarily transfers them to another location
> 3. Housing units that are a unit unavailable for rent
> 4. Rooms for rent in an owner-occupied home
> 5. Housing units in hotels, motels, inns, bed and breakfasts, or in similar accommodations that provide lodging for guests
> 6. Housing units in facilities licensed or required to be licensed such as Assisted Living Facilities, Adult Family Homes, or Soldiers' and Veteran's Homes (as stated in: RCW 18.20, RCW 70.128, or RCW 72.36)
> 7. Housing units in any state licensed hospital, hospice, community-care facility, intermediate-care facility, or nursing home
> 8. Housing units in any convent, monastery, or other facility occupied exclusively by members of a religious order or congregation
> 9. Emergency or temporary shelter or transitional housing accommodations
> 10. Housing units owned, operated, or managed by a major education or medical institution or by a third party for the institution
> 11. Housing units that a government entity or housing authority owns, operates, or manages; or units exempted from municipal regulation by federal, state, or local law"

What this means for P.I.E.R.: Seattle Housing Authority buildings, university housing, hospitals, care homes, shelters and owner-occupied room rentals will show up as "never registered" in the data but do not have to register. Each never-registered lead (output C) has to be checked against this list before it is counted.

### 1.4 Penalties

From the SDCI PDF "RRIO Program Fees" (https://www.adc.seattle.gov/documents/Departments/SDCI/Codes/RRIO/RRIOProgramFees.pdf):

> "If a property owner does not register their property or complete an inspection by the due date, the City may issue a Notice of Violation and begin assessing financial penalties as provided in Section 22.214.086 of the Seattle Municipal Code. The code allows for cumulative civil penalties of $150 per day for the first ten days and $500 per day thereafter."

From the SDCI PDF "RRIO Penalties and Violations" (https://www.seattle.gov/documents/Departments/SDCI/Codes/RRIO/RRIOViolationsandPenaltiesFlyer.pdf):

> "Once the due date has passed, we will send a warning letter by postal mail and email to remind you of the requirement that was missed and warn that a violation and penalties may occur if you do not take action. A $52.50 mandatory late fee is added to late registrations and overdue inspections."
>
> "If you do not take the required action by the date specified in the warning letter, we will issue a Notice of Violation letter. The notice will provide a compliance date to meet the RRIO requirement. After that date, penalties begin to accrue."

What this means for P.I.E.R.: penalties only start **after a Notice of Violation's compliance date**, and SDCI says it "may reduce the applicable penalties". So a gap in registration does not by itself mean any penalty was owed. **The code does not count penalties.** Per the transfer note (section 4.6), no penalty estimate is made until SMC 22.214.086 itself is read.

---

## 2. The fees (step 2)

From the official SDCI PDF "RRIO Program Fees" (PDF title "Seattle SDCI - RRIO Program Fees", created 2025-11-25, modified 2026-01-06):

> "RRIO registration is valid for 2 years. As of January 2026, the registration fee is $126 for each property, which includes the first rental unit, plus $31.50 for each additional unit at the same property."
>
> "A late fee of $52.50 will be applied for overdue registrations and inspections."
>
> "Note: fees above include the RRIO fees and a 5% SDCI technology fee."

| Fee (as of January 2026) | Amount | Source |
|---|---|---|
| Registration, per property, 2 years, includes first unit | $126.00 | SDCI RRIO Program Fees PDF |
| Each additional unit at the same property | $31.50 | same |
| Late fee, overdue registration or inspection | $52.50 | same, and RRIO Penalties and Violations PDF |
| City inspection, per property incl. first unit | $241.50 | same |
| City inspection, each additional unit | $52.50 | same |
| Private-inspector filing fee | $63.00 | same |

**Older amounts are not confirmed.** The transfer note listed $110 per property, $20 per extra unit and a $31.50 late fee from older SDCI documents. Those are kept in `code/fee_schedule_RRIO.json` but marked `verified: false`, with a guessed start date. Most gaps since 2020 began before 2026, so **the fee calculation (output F) for those gaps is not reliable until the older official fee amounts and their dates are confirmed.**

---

## 3. The build code (step 3)

Folder: `docs/pier_handoff_2026-11-11/code/`

| File | What it is |
|---|---|
| `pier_registration_gaps.py` | Builds outputs A–F. Python 3, standard library only (`shapely` only if a district map file is given). |
| `fee_schedule_RRIO.json` | Fee amounts with source, start date and a verified flag. |
| `../tests/test_pier_registration_gaps.py` | 14 tests on made-up SAMPLE rows. |

**It has not been run on real data.** It was tested only on a handful of made-up rows whose addresses all contain the word SAMPLE. All 14 tests pass. That shows the logic does what it says on those rows, nothing more.

### 3.1 What it does

- **A. `rrio_registration_periods`** — one row per registration period per address, with start date, expiration date, where each date came from (file and row), and units.
- **B. `rrio_registration_gaps`** — every gap that started on or after January 1, 2020: start, end (or "still open as of 2025-11-20"), days, units, district, whether the address later renewed, late-registration violations in the gap, registration-expired status rows, and ownership transfers in the gap.
- **C. `unregistered_candidates`** — addresses with evidence they may be rentals but no RRIO registration on file: King County parcels (once the file is named), landlord-tenant records with no RRIO match, the 159 REG-03 complaints, and RRIO violations at addresses with no registration.
- **D. `evictions_without_registration`** — each eviction filing labeled: covered, in a gap, before the first registration, never registered on file, undetermined, or could not match. Waits for the eviction file.
- **E. `complaints_during_gaps`** — complaints, notices of violation, citations and rent-increase complaints opened during a gap.
- **F. `rrio_money_estimate`** — fee calculation per gap, labeled "CALCULATION ONLY - not a record of money owed, charged or unpaid". Late fees shown as "late fees the schedule would apply".

### 3.2 Safety rules built in

- **Unknown column headers stop the run** and list every unknown header. The known headers are the ones in the Drive "Traceability Document: Merging Seattle Rental Property Registration and RRIO Datasets" (and its 2023 load log), plus the ones in the P.I.E.R. skills. Nothing is guessed.
- **Bad bytes stop the run.** The two snapshot files that failed before (`_20250506`, `_20250731`) will stop it with the byte position, unless `--allow-cp1252-fallback` is given; that choice is written to the run log.
- **Files with 0 valid rows are named in the log**, not dropped silently (for example `_20250908`).
- **Nothing expiring on or after 2025-11-20 is called lapsed.** It is labeled "expires after data end - unknown".
- **A registration with no known expiration date does not create a gap.** It is listed in `rrio_coverage_unknown`. Only if Kimberly passes `--assumed-term-years 2` does the code estimate an end date, and every such row is labeled `ESTIMATED`.
- **It writes its own new database file**, `pier_registration_gaps_DRAFT.sqlite`. It refuses to write into `stlca_property_intelligence.sqlite`. Adding these tables to P.I.E.R. needs Kimberly's approval.
- Every output row keeps the source file and row number for its dates.

### 3.3 How Kimberly runs it (on her computer)

Open the folder that holds the RRIO files in File Explorer, Shift + right-click on empty space, choose "Open PowerShell window here", then:

1. Check every file's headers first (fast, changes nothing):
   ```
   python pier_registration_gaps.py --check-headers --rrio-dir . --snapshot-dir .
   ```
2. If that passes, build A, B, C, E and F:
   ```
   python pier_registration_gaps.py --rrio-dir . --snapshot-dir . --complaints "PATH\TO\MASTER_SOURCE_CITYWIDE_LLT_THRU_20251231_ENRICHED_01272026__PLUS_RECORDLIST-RARE.csv" --topics "PATH\TO\landlord-tenant-records.csv" --reg03 "PATH\TO\REG03_unregistered_or_lapsed_complaints_2020_2025_DRAFT.csv" --fee-schedule fee_schedule_RRIO.json --out-dir pier_gaps_out
   ```
3. When the eviction file and King County file are known, add:
   ```
   --evictions FILE.csv --evictions-address-col "COLUMN" --evictions-date-col "COLUMN" --evictions-id-col "COLUMN"
   --kc-file FILE.csv --kc-address-col "COLUMN" --kc-units-col "COLUMN" --min-units N
   ```

Results land in `pier_gaps_out\`: one `_DRAFT.csv` per output, `RUN_LOG.txt`, `MANIFEST.json`, and the draft SQLite file.

### 3.4 Known limits

- Address-only join. One address can be several buildings; one building can have several addresses. A failed match is not proof a property is unregistered.
- The snapshots only list registrations that were current when each snapshot was taken. Older periods come from RRIO registration and renewal events, which have no expiration date. Without `--assumed-term-years`, many older periods will be "end unknown" and their gaps will not be computed. That is on purpose.
- RRIO record numbers and snapshot registration numbers are matched only when they are equal. Whether they use the same numbering has not been checked on real data.
- Late-registration violations are matched to a gap by address and date, not by registration number.
- The eviction and King County files have unknown headers, so their column names must be typed on the command line.
- Exemptions (section 1.3) are not applied automatically. Each lead needs a manual check.

---

## 4. Wording rules for anything that comes out of this

- "N eviction filings were made at addresses with no RRIO registration on file on the filing date, based on the records reviewed." Never "should not have been evicted."
- Fee numbers are "calculated from the SDCI fee schedule", never "owed" or "uncollected".
- Every number names its source file and date range, and says whether it counts rows, addresses or buildings.

## Sources

- SDCI, Just Cause Eviction Ordinance page: https://www.seattle.gov/sdci/codes/codes-we-enforce-(a-z)/just-cause-eviction-ordinance
- SDCI, RRIO Registration Exceptions (PDF): https://www.seattle.gov/documents/Departments/SDCI/Codes/RRIO/RRIORegistrationExceptions.pdf
- SDCI, RRIO Penalties and Violations (PDF): https://www.seattle.gov/documents/Departments/SDCI/Codes/RRIO/RRIOViolationsandPenaltiesFlyer.pdf
- SDCI, RRIO Program Fees (PDF): https://www.adc.seattle.gov/documents/Departments/SDCI/Codes/RRIO/RRIOProgramFees.pdf
- Not readable from this session: Municode SMC 22.206.160 / Chapter 22.205 / Chapter 22.214; City Clerk code pages.
- Drive: "Traceability Document: Merging Seattle Rental Property Registration and RRIO Datasets" (column headers).
