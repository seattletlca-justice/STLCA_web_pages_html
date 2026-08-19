# STLCA Web Pages — To-Do

Status as of 2026-08-19: repo contains only a README stub and the raw source
dataset (`input/case_nov_MASTER_SOURCE_CITYWIDE_LLT_THRU_20251231_ENRICHED...csv`).
No HTML pages exist yet.

## Data
- [ ] Document the schema/columns of the citywide CSV in `input/`
- [ ] Decide on a per-district / per-property extraction approach (see `stlca-extract` skill)
- [ ] Run findings through `stlca-verify` before anything gets published

## Site structure
- [ ] Define the page set (homepage, district pages, individual case/property pages, methodology page)
- [ ] Pick a static-site approach (plain HTML/CSS vs. a generator) and scaffold the directory layout
- [ ] Set up a build/deploy step (GitHub Pages or similar)

## Content
- [ ] Draft homepage framing and hero copy — run through `stlca-redteam` before publishing
- [ ] Build first district or case-study page as a template for the rest
- [ ] Write the methodology/sourcing page (what the data is, how it was verified)

## Housekeeping
- [ ] Flesh out `README.md` with project purpose and setup instructions
- [ ] Add `.gitignore` if the raw CSV or generated output shouldn't all be tracked
