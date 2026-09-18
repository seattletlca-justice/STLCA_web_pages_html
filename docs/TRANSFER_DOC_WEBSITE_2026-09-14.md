# Website Transfer Doc — 2026-09-14

Written for whichever session (chat, Cowork, or a fresh Code session) picks up the website side of tonight's work next. Companion to the pipeline-side transfer doc and memory in `stlca_pipeline` — this doc is website-specific.

## 1. This repo is new and nearly empty — that's fine, it's the real destination

`STLCA_web_pages_html` had only a README and two citywide master CSVs in `input/` before tonight. As of this commit it also has `case-studies/8201-aurora-ave-n.html` — the first real page. This appears to be the intended, version-controlled home for website HTML going forward, distinct from two other locations discovered tonight that are **not** this repo and should not be confused with it:

- `C:\STLCA_PRO\STLCA_R.A.R.E._WEB\seattle-are-static-inline\` — a separate, already-built static site (not in git, no source project found anywhere on this machine). Pages: `index.html`, `pages/{case-studies,council-briefing,dataset-dashboard,enforcement-outcomes,inspection-visibility,methodology,record-engine,404}.html`. Each is 2.7–5.9MB, bundled (framework output, not hand-editable HTML — looks like a Vite/React export with everything inlined). `record-engine.html` is the "8 modules" engine-explainer page Kimberly said she loves the look of (Driver, Harvester, Gatekeeper, Signal, Linker, Auditor, Archivist, Analyst). `case-studies.html` in that folder is a real, empty shell — real title and meta description, zero property content. **Do not hand-edit these bundled files** — if a real source project for them exists, find it before touching them; a blind text edit on a multi-MB bundle risks breaking it with no way to verify the diff.
- `STLCA_WEB\WEBSITE_COPY_PAGES_NOT_LIVE\` — **moved during this same session to live inside this repo** (was `C:\STLCA_PRO\STLCA_WEB\...`, Kimberly relocated it mid-session; if it's not there, check `C:\STLCA_PRO\STLCA_WEB\` directly as a fallback). Small, genuinely hand-editable HTML files — `NOT_LIVE_investigation-oversight.html`, `NOT_LIVE_investigation-complaint-record.html`, and a third, `NOT_LIVE_investigation-closing.html`, not yet reviewed as of this doc. Figma-sourced, navy/gold design system, the actual card-click-through template the Everspring page's evidence ledger (§4) is built from. These ARE meant to be edited directly — small, clean, no bundler. Now colocated with `case-studies/8201-aurora-ave-n.html` in this same repo, which simplifies things: template and first built page are no longer in separate, disconnected folders.

**Open question, unresolved:** is there a real source project (React/Vite/etc.) behind the `STLCA_R.A.R.E._WEB` bundle, and if so, where does it live? Not found on this machine tonight. Ask Kimberly before assuming either "hand-edit the bundle" or "there's no source, treat the bundle as the source of truth" — both are live possibilities and the wrong guess breaks something.

## 2. Naming: it's R.A.R.E., not A.R.E.

The `seattle-are-static-inline` folder name is shorthand — the actual page content (see the record-engine.html hero) says **"R.A.R.E." / "Records Accountability Review Engine"** explicitly, in Kimberly's own words on her own built page. Use that expansion. The folder name is not a rebrand signal.

## 3. Design direction, from tonight's research — narrative + ledger, not one or the other

Looked at three real precedents before building anything:
- **RRIO's own annual report** (Seattle's rental-registration program): leads with specific, countable categories — "1,516 improperly installed electrical," "1,237 missing smoke alarms" — not vague summaries. The Council-briefing memo already in this project does this citywide; property pages should do it per-property.
- **Seattle Fire Department's annual report**: opens with a human voice (Chief's message), keeps hard data in the middle, closes with people/recognition. Credibility bookends around the numbers.
- **ProPublica's actual investigative housing pieces** (closest real match to this project's ambition): narrative prose carries the story, named sources on both sides quoted directly, data embedded inline with the prose rather than siloed in a separate dashboard, ends with bylines and a correction/methodology note.

**Conclusion applied to `case-studies/8201-aurora-ave-n.html`:** one page, two layers. A ProPublica-style narrative section up top (the story a journalist or council staffer actually reads) that scrolls directly into a card-based, record-by-record evidence ledger (what a lawyer needs to build a case from — this part reuses the exact `STATES`-array click-through mechanism from `NOT_LIVE_investigation-complaint-record.html`, adapted). They are not competing formats; the narrative's job is to get someone to keep scrolling into the ledger, and every specific claim in the narrative should be traceable to a specific record in the ledger below it.

## 4. What's actually in `case-studies/8201-aurora-ave-n.html` right now

Navy/gold design system, matching the existing `NOT_LIVE_investigation-*.html` family (`--navy:#0a1628`, `--gold:#f5a623`, Newsreader serif for display, system sans for body, mono for record numbers/data). Structure, top to bottom:

1. Masthead — address, QA/verify/redteam status badges, stat tiles, ownership strip
2. Narrative — the SPD nuisance-declaration timing, SMC 10.09 explained (it governs the owner, not tenants — this correction matters, see §5), the 14-complaint cluster, the $164K Rapid Rehousing figure, the NOV
3. Chronological ledger — 2018 (1 record) → Aug–Oct 2020 cluster (15 records, `<details>` rows, click to expand) → Jul–Aug 2021 NOV chain (full six-stage click-through: Intake/Inspection/Finding/Enforcement/Correction/Closure)
4. Property History + Held for Human Review (two-column)
5. Evidence Index — every source file named, real ones marked "in hand," two marked "unreadable" (scanned PDFs, no text layer)

Every fact traces to a real file in `stlca_pipeline/outputs/D6_8201 AURORA AVE N_20260914_073553/` or to a specific news article/primary document verified tonight (see §5). Status: **DRAFT, held for review, not yet redteamed** — that badge is in the page itself, keep it there until an actual `stlca-redteam` pass happens.

## 5. Corrections made tonight, in order of how much they matter

- **NOV violation count: 148, not 113.** A real pipeline bug (`extractor.py`, `_extract_numbered_violations()`, ~line 2971) truncates the violations list at the first inline "SEE NOTE XX" cross-reference that happens to line-wrap onto its own line. Not yet fixed in the pipeline — this page's number is hand-corrected from the complete 12-page NOV text.
- **The SPD "agreement" framing.** An earlier draft (both an older local case-study HTML and a separate artifact from another chat session) said SPD "denied" any nuisance agreement existed. That's wrong — SPD signed a Correction Agreement five days *after* the eviction notices went up, per direct verification of the actual PubliCola article. Kimberly's own correction on this, which the current narrative follows: the paperwork timing is a side issue — SMC 10.09's Correction Agreement mechanism governs the owner's obligation to abate a nuisance and has nothing to do with tenants; the real point is that the City had independent notice (SPD's own July nuisance letter) a full month before the eviction and nothing in the record shows intervention while it was happening.
- **$164,000 Rapid Rehousing figure: real, now confirmed.** Sourced to a Seattle Times article (2018, largest single recipient of Rapid Rehousing funds among all city landlord/vendor contracts that year). An earlier pass this session said this figure was unsourced — it wasn't, it just hadn't been found yet.
- **5 rapes / 1 homicide, not 6/2.** Use the number from the actual signed SPD Chronic Nuisance Declaration letter (Chief Carmen Best, July 20 2020, real SPD incident numbers per entry) — that's a primary document. A web-search summary surfaced "6 rapes, 2 homicides" during tonight's research; that number could not be traced to any primary source and should not be used.
- **Inspector name on the NOV: Stephen Hinch,** confirmed from the complete NOV text (signature block). An earlier draft used "Dustin Rasmussen" — wrong, not used anywhere in tonight's build.
- **Ownership: Next Wave Investments LLC, agent Myung Ha Kang** — confirmed via a direct WA Department of Revenue business-lookup (UBI 604-168-802), independent of SDCI. "Ryan Kang" is a real, separately-sourced name too (the NOV's own mailing block, and used independently in Seattle Times/PubliCola coverage) — likely the same family, relationship not established, don't merge the two names into one without a source that actually connects them.

## 6. Next up, in order

1. Two more R.A.R.E. runs were kicked off tonight and should be finished or close to it: **Lowell Emerson (1102/1110 8th Ave, D7)** and **The Addison (308 4th Ave S, D2)** — check `stlca_pipeline/outputs/` for folders starting `D7_1102` and `D2_308`. Once QA status is known, repeat the same process this doc describes: verify against primary sources first (don't trust any existing draft's numbers), then build the narrative+ledger page the same way.
2. A fourth property, **101 6th Ave S (D2)**, already has a passing run from 2026-09-12 sitting in `outputs/` — no fresh run needed, just verify-and-build.
3. Kimberly's stated goal: a case study in every district (7 total), used both to pitch media and as the evidentiary backbone under the site's existing dashboards/datasets — eventually a paid product. Nothing about that changes how each individual page should be built: verify first, narrative-plus-ledger, every claim traceable, publication hold until `stlca-redteam` actually runs.
4. This repo has not been committed to yet tonight — the new file is sitting untracked. Not committed without Kimberly's go-ahead, per standing practice this session.
