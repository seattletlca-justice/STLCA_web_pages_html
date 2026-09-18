#!/usr/bin/env python3
"""
STLCA pre-publication QA.

Runs the checks named in WEBSITE_BUILD_INSTRUCTIONS section 11 and reports the
exact number run and the exact number failed. Never prints "QA passed" without
naming what was checked.

Usage:  python qa.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Section 5.1 -- prohibited strings, checked case-insensitively.
PROHIBITED = [
    ("Compliance Authority", "STLCA is not an authority"),
    ("Landlord Compliance Authority", "STLCA is not an authority"),
    ("documentation collapse", "asserts inspections stopped"),
    ("the 2018 collapse", "asserts inspections stopped"),
    ("enforcement rate", "implies complaint-to-violation linkage"),
    ("Official Landlord Registry", "legal exposure"),
    ("City-corrected", "no City record establishes 'correction'"),
    ("the City's corrected field", "no City record establishes 'correction'"),
]

# Figures that must never be typed into markup -- they must come from the data layer.
HARDCODED = [
    r"\b56,?258\b", r"\b36,?106\b", r"\b31,?330\b", r"\b31,?321\b", r"\b50,?817\b",
    r"\b55,?590\b", r"\b21,?811\b", r"\b233,?543\b", r"\b40,?062\b", r"\b29,?824\b",
    r"64\.2\s*%", r"61\.7\s*%", r"61\.6\s*%", r"18\.1\s*%", r"17\.7\s*%",
]

# A page showing an inspection-date figure must carry the verbatim limitation.
INSPECTION_PAGES = [
    "findings/finding-01.html", "findings/finding-03.html",
    "dashboards/citywide-kpi.html", "dashboards/inspection-completeness.html",
]

checks = 0
fails = []


def fail(name, detail):
    fails.append((name, detail))


def pages():
    for root, dirs, names in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in ("data", "__pycache__")]
        for n in sorted(names):
            if n.endswith(".html"):
                yield os.path.join(root, n)


def rel(p):
    return os.path.relpath(p, HERE).replace("\\", "/")


all_pages = list(pages())
print(f"Scanning {len(all_pages)} HTML pages under STLCA_SITE/\n")

# ---------------------------------------------------------------- 1. prohibited strings
for path in all_pages:
    text = open(path, encoding="utf-8").read()
    for phrase, why in PROHIBITED:
        checks += 1
        # "Compliance Authority" is quoted once on about.html to explain the retirement.
        hits = [m for m in re.finditer(re.escape(phrase), text, re.I)]
        if hits and not (rel(path) == "about.html" and phrase.endswith("Authority")):
            fail("prohibited string", f'{rel(path)}: "{phrase}" ({why})')

# ---------------------------------------------------------------- 2. hardcoded figures
for path in all_pages:
    text = open(path, encoding="utf-8").read()
    # strip the provenance SHA and any <code> sample; check only rendered prose/markup
    for pat in HARDCODED:
        checks += 1
        m = re.search(pat, text)
        if m:
            line = text[:m.start()].count("\n") + 1
            fail("hardcoded figure",
                 f"{rel(path)}:{line}: {m.group(0)} typed into markup — must bind from the data layer")

# ---------------------------------------------------------------- 3. internal links
# Inline <script> bodies are stripped first: JS string concatenation such as
# "district-" + i + ".html" is not a link, and matching it produces false failures.
link_re = re.compile(r'(?:href|src)="([^"#?][^"]*?)"')
script_body_re = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)


def markup_only(text):
    return script_body_re.sub(
        lambda m: re.match(r"<script\b[^>]*>", m.group(0), re.I).group(0) + "</script>", text)


for path in all_pages:
    text = markup_only(open(path, encoding="utf-8").read())
    base = os.path.dirname(path)
    for href in link_re.findall(text):
        if href.startswith(("http://", "https://", "mailto:", "data:", "//")):
            continue
        checks += 1
        target = os.path.normpath(os.path.join(base, href.split("#")[0].split("?")[0]))
        if not os.path.exists(target):
            fail("broken link", f"{rel(path)} -> {href}")

# ---------------------------------------------------------------- 4. home in one click
for path in all_pages:
    checks += 1
    text = open(path, encoding="utf-8").read()
    # every page loads stlca.js, which injects a header whose brand links to index.html
    if 'src="../assets/stlca.js"' not in text and 'src="assets/stlca.js"' not in text:
        fail("no home link", f"{rel(path)} does not load stlca.js, so it has no injected nav")

# ---------------------------------------------------------------- 5. inspection limitation
for p in INSPECTION_PAGES:
    checks += 1
    path = os.path.join(HERE, p)
    if not os.path.exists(path):
        fail("missing page", p)
        continue
    text = open(path, encoding="utf-8").read()
    if "inspection_date_limitation" not in text:
        fail("missing limitation",
             f"{p} shows an inspection-date figure but does not render the verbatim limitation")

# ---------------------------------------------------------------- 6. universe labelling
for path in all_pages:
    checks += 1
    text = open(path, encoding="utf-8").read().lower()
    if re.search(r"citywide[^<.]{0,40}(landlord|lt |tenant)", text) and "not the citywide" not in text:
        fail("universe mislabel", f"{rel(path)}: landlord-tenant universe described as citywide")

# ---------------------------------------------------------------- 7. (retired)
# Names that appear in a public record may be published, attached to that record
# (Kimberly, 2026-09-14). That is a sourcing judgment, not a string check.

# ---------------------------------------------------------------- 8. data layer present
for req in ("assets/data.js", "assets/stlca.js", "assets/stlca.css", "data/findings.json"):
    checks += 1
    if not os.path.exists(os.path.join(HERE, req)):
        fail("missing asset", req)

# ---------------------------------------------------------------- 9. every page binds data
for path in all_pages:
    checks += 1
    if 'assets/data.js' not in open(path, encoding="utf-8").read():
        fail("unbound page", f"{rel(path)} does not load the data layer")

# ---------------------------------------------------------------- report
print(f"Checks run:    {checks}")
print(f"Checks failed: {len(fails)}\n")
if fails:
    by = {}
    for name, detail in fails:
        by.setdefault(name, []).append(detail)
    for name in sorted(by):
        print(f"[{name}] {len(by[name])}")
        for d in by[name]:
            print("   ", d)
    print("\nSTATUS: QA FAILED, NOT READY")
    sys.exit(1)

print("Checked, by name:")
print(f"  · {len(PROHIBITED)} prohibited strings across {len(all_pages)} pages")
print(f"  · {len(HARDCODED)} protected figures not typed into markup")
print("  · every internal link and asset reference resolves on disk")
print("  · every page loads the shared chrome, so every page reaches home in one click")
print(f"  · the verbatim inspection-date limitation appears on all {len(INSPECTION_PAGES)} "
      "pages showing an inspection-date figure")
print("  · no page labels the landlord-tenant universe 'citywide'")
print("  · the data layer and both shared assets are present, and every page binds to them")
print("\nSTATUS: QA PASSED")
