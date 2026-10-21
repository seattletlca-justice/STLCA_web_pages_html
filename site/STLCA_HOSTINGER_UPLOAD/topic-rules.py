#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llt_issue_rules.py  -  evidence-built issue rules for the SDCI landlord-tenant complaint descriptions
=====================================================================================================
Reads an approved LLT JSON (a list of records with RECORDNUM, RECORDTYPE, DESCRIPTION, DESCRIPTION1, DISTRICT ...),
reads the actual DESCRIPTION text of every COMPLAINT record, and writes an audit folder:

  LLT_vocab_audit.html        one-file review page (open by double-click)
  rules_with_examples.csv     every rule: pattern, counts, one exact example from the records, self-test result
  match_audit.csv             EVERY match and EVERY rejection: record ID, rule, decision, reason, phrase, context
  record_issues.csv           one row per complaint: authorship, lane, categories, distinct-issue count, full text
  manual_review_pocket.csv    borderline cases (nothing forced into a category) - fill in 'decision' and feed back
  unmatched_statements.csv    descriptions where no issue wording was found
  old_vs_new_all_disagreements.csv   every complaint where the old script and these rules disagree, with record ID
  vocab_*.csv, city_labels.csv, old_vs_new_*.csv, district_*.csv

How the counting works (the rules in this file are the single source of truth):
  * City labels (POTA, JCEO, TRAO, EDRA, RRIO, HBMC, CSB, SMC/RCW cites ...) are masked before matching, so they can
    never be counted as tenant vocabulary. The staff wrapper "Per online complaint:" / "POTA--per phone call--" is
    masked too and recorded as the channel.
  * Words fused by a dropped line break ("rentincrease", "thelandlord") are repaired using the records themselves.
  * Each rule is STRONG (a phrase that is a problem on its own), PRESENCE (a problem word, rejected when negated:
    "no mold"), COMPOUND (an object word + a failure word in the same clause: "heat has not been working"),
    or WEAK (ambiguous - goes to the manual review pocket, never counted).
  * One piece of wording is claimed by one category (a leaking toilet is plumbing, not also "leaks").
  * A record counts once per category; separate problems each count ("no heat, mold, plumbing" = 3 issues).
  * Every rule carries an exact example copied from the records; the script re-checks that each rule still
    reproduces its example before it analyses anything (self-test).

Run (from the folder that holds this script and rare_district_story_parser.py), one line:
    python llt_issue_rules.py "C:\\STLCA_PRO\\STLCA_DATA\\LLT_APPROVED_THROUGH_20251231.json" --out llt_vocab_audit
Optional:
    --decisions decisions.csv     your ACCEPT / REJECT choices for borderline cases (columns record_id,category,decision)
    --parser-dir DIR              folder with rare_district_story_parser.py (default: next to this script)
    --workers N                   processes (default: CPU count - 1)
    --self-test-only              just check that every rule reproduces its example
This script only READS the JSON. It writes only inside --out.
"""
import argparse, shutil, os, sys, json, re, csv, math, random, time, hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone


# ====================================================================================================
# TEXT PREPARATION
# ====================================================================================================
"""Text preparation: cleaning, city-label masking, staff-prefix channel, authorship, glue repair, language."""
import re
from collections import Counter

def clean(t):
    t = (t or '')
    t = t.replace('\xa0', ' ').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
    t = t.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-')
    return re.sub(r'\s+', ' ', t).strip()

# ---- city / staff labels that must never be counted as tenant vocabulary
LABEL_RX = re.compile(
    r"\b(?:POTA|TRAO|JCEO|EDRA|RRIO|HBMC|HZT|HZW|CSB|RARO|ROFR|INRENT|RENTAG|PAOTHR|OTHR|L/T|H/Z|SDCI|DPD)\b"
    r"|\bSMC\s*\d{2}\.\d{3}(?:\.\d{3})?(?:\.[A-Z])?\b|\bRCW\s*\d{2}\.\d{2}(?:\.\d{3})?\b|\bSR\s*#?\s*\d{2,}(?:-\d+)?\b|\bPRE-?REG(?:ISTRATION)?\b", re.I)
# the labels are matched case-insensitively only when written in capitals or as the known acronyms
LABEL_CASE_RX = re.compile(r"\b(?:POTA|TRAO|JCEO|EDRA|RRIO|HBMC|HZT|HZW|CSB|RARO|ROFR|INRENT|RENTAG|PAOTHR|OTHR|L/T|H/Z|SDCI|DPD)\b")
LABEL_REST_RX = re.compile(r"\bSMC\s*\d{2}\.\d{3}(?:\.\d{3})?(?:\.[A-Z])?\b|\bRCW\s*\d{2}\.\d{2}(?:\.\d{3})?\b|\bSR\s*#?\s*\d{2,}(?:-\d+)?\b|\bPRE-?REG(?:ISTRATION)?\b", re.I)

CHANNEL_RX = re.compile(
    r"^\W*(?:(?:[A-Z]{3,10}(?:\s*[,&/;]\s*[A-Z]{3,10})*)\s*[-:]+\s*)?"
    r"per\s+(?P<ch>on\s*-?\s*line|online|phone|telephone|mailed|e-?mail|letter|walk[- ]?in|fax|csb|call|in\s*person|handwritten|text|voicemail|complaint)"
    r"(?:\s+(?:complaint|call|conversation|letter|form|submission))?(?:\s*,?\s*dated\s+[\d/]+)?\s*[-:;,\"]*\s*", re.I)

OTHER_LABELS = r"(?:POTA|TRAO|JCEO|EDRA|HBMC|HZT|HZW|CSB|RARO|ROFR|INRENT|RENTAG|PAOTHR|OTHR|L/T|H/Z|SDCI|DPD)"

def rrio_is_label(text, s, e):
    """RRIO is both a staff label and a program tenants talk about ('does not have a RRIO', 'the RRIO checklist').
    It is a label only in label position: followed by punctuation, inside a list of labels, an intake subject line, or the whole text."""
    after = text[e:e + 40]; before = text[max(0, s - 40):s]
    if not text[:s].strip(' :;,-/&') and not text[e:].strip(' :;,-/&.'): return True
    if re.match(r"\s*[:;,/=&-]", after): return True
    if re.match(r"\s*(?:REG\b|Inspection\s*[-:/]|Rent\b)", after): return True
    if re.search(OTHER_LABELS + r"\s*[,;&/-]*\s*$", before): return True
    if re.match(r"\s*[,;&/-]*\s*" + OTHER_LABELS + r"\b", after): return True
    return False

def mask_labels(text):
    labels = []
    def rep(m):
        if m.group(0) == 'RRIO' and not rrio_is_label(text, m.start(), m.end()):
            return m.group(0)
        labels.append(m.group(0).upper()); return ' ' * len(m.group(0))
    text = LABEL_CASE_RX.sub(rep, text)
    text = LABEL_REST_RX.sub(rep, text)
    return text, labels

def channel_of(text):
    m = CHANNEL_RX.match(text)
    if not m: return None, 0
    ch = re.sub(r'[\s-]+', '', m.group('ch').lower())
    ch = {'online': 'online', 'phone': 'phone', 'telephone': 'phone', 'call': 'phone', 'csb': 'csb', 'inperson': 'inperson', 'walkin': 'walkin'}.get(ch, ch)
    return ch, m.end()

FIRST = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|my|me|mine|we|we're|we've|our|us|myself)\b", re.I)
STAFFMARK = re.compile(r"\b(?:complainant|complaintant|complainanat|compl\b|caller|tenant states|tenants state|tenant says|tenant reports|resident states|reporting party|mgr says|manager says|she says|he says|they say|she stated|he stated|staff|spoke with|left message|advised|referred|transferred|inspector|noted|note:|per tech|forwarded from)", re.I)
WORKFLOW_RX = re.compile(r"\b(?:hold|holding|holds|released?|remov\w*|initiat\w*|packet|waiver|certification|application|permit|license|assistance|help|appointment|questions?|request|need|needs|process|start)\b", re.I)

def workflow_of(labels, masked):
    """TRAO/EDRA labelled staff notes about permit holds etc. - not a tenant statement."""
    if not any(l in ('TRAO', 'EDRA') for l in labels): return False
    words = re.findall(r"[A-Za-z']+", masked)
    if len(words) > 14: return False
    if FIRST.search(masked): return False
    return bool(WORKFLOW_RX.search(masked))

def authorship(raw, labels=None, masked=None):
    t = clean(raw)
    if not t: return 'EMPTY'
    if re.search(r'where is the vegetation|what safety issue|photo link|servicerequest', raw or '', re.I): return 'FORM_TEMPLATE'
    if labels is not None and masked is not None and workflow_of(labels, masked): return 'STAFF_WORKFLOW_NOTE'
    if labels and masked is not None and len(re.findall(r"[A-Za-z]{2,}", masked)) <= 1: return 'STAFF_LABEL_ONLY'
    ch, end = channel_of(t)
    if ch in ('phone', 'csb', 'walkin', 'inperson', 'voicemail', 'fax'): return 'STAFF_PHONE_SUMMARY'
    if ch == 'online': return 'ONLINE_FORM_TEXT'
    if ch in ('mailed', 'letter', 'handwritten', 'email', 'e-mail', 'text', 'complaint'): return 'STAFF_RELAY_OF_WRITTEN'
    if re.search(r'\bSMC\b|\bRCW\b', t) and len(t.split()) <= 12: return 'STAFF_CODE_LABEL'
    first = bool(FIRST.search(t)); staff = bool(STAFFMARK.search(t))
    words = len(re.findall(r"[A-Za-z0-9']+", masked if masked is not None else t))
    if words <= 6 and not first: return 'SHORT_UNATTRIBUTED'
    if first and not staff: return 'TENANT_FIRST_PERSON'
    if staff and not first: return 'STAFF_THIRD_PERSON'
    if first and staff: return 'MIXED_MARKERS'
    return 'NEUTRAL_UNATTRIBUTED'

# ---- language
ES = set("el la los las de que y en un una por con para no se mi su es esta está hay pero como más muy nos le lo del al sin sobre también porque cuando donde ya ha han estoy tengo tiene propietario inquilino alquiler renta edificio apartamento casa agua calefacción por favor ayuda arreglar".split())
EN = set("the and of to in is it that for on with as was are be this have not at but from by or an they we you he she his her their our my me i".split())
def language_of(text):
    t = clean(text)
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 12: return 'short'
    nonlat = sum(1 for c in letters if ord(c) > 0x24F)
    if nonlat / len(letters) > 0.3: return 'other_script'
    ws = re.findall(r"[a-záéíóúñü]+", t.lower())
    es = sum(1 for w in ws if w in ES); en = sum(1 for w in ws if w in EN)
    if len(ws) >= 6 and es >= 4 and es > 1.5 * en: return 'es'
    return 'en'

# ---- glue repair (dropped line breaks fuse two words: rentincrease, thelandlord, 3-daynotice ...)
FW = set("the a an and or but of to in on at by for from with without about regarding because during any our my your their his her its they he she we i you it that this these those what who which per not no has have had been be is are was were does did do will would can could should may might also still now then than as if so since until after before being having doing getting".split())
PROTECT = set("""outdoor outdoors indoor indoors without within upstairs downstairs bedroom bedrooms bathroom bathrooms basement landlord landlords tenant tenants baseboard baseboards doorknob doorknobs doorbell doorway doorways doorframe doorframes bedbug bedbugs cockroach cockroaches mailbox mailboxes somewhere something someone anything anyone everyone everything nothing sometimes however whatever whenever wherever already always another because before between beyond cannot elsewhere inside outside overnight overflow overflowing overhead overall overcrowded overcrowding overgrown overheating pathway pathways playground rooftop rooftops sidewalk sidewalks somewhat stairway stairwell stairwells sunlight therefore throughout together underneath understand unlawful weekend weekends whatsoever workday workers wastewater watertight stormwater rainwater groundwater newspaper plumbing handrail handrails hardwood hotline lifetime lightbulb limited nightly nighttime daytime fireplace household homeowner homeowners background heather windowsill inconsistently inconsistent inconsistency incomplete intolerable insufficient inadequate unreasonable unresponsive uninhabitable unsanitary onsite offsite""".split())

ANCHORS = sorted("notice rent lease landlord tenant eviction evict deposit water heat mold mildew leak roach bedbug sewage elevator electrical plumbing repair increase vacate harass retaliation relocation inspection violation management".split(), key=len, reverse=True)
REAL_WORDS = set("""noticeable noticeably rented renter renters rentals rental renting leased leasing heated heater heaters heating heathen moldy molded molding mildewy waterproof waterfall waterfront watering watercolor repaired repairing repairman repairs increased increases increasing vacated vacating harassed harassing harassment inspections inspected inspector inspectors violations violated management manager managers managed""".split())

def build_glue_map(texts):
    tok = re.compile(r"[A-Za-z]+")
    df = Counter(); bi = Counter()
    for t in texts:
        ws = [w.lower() for w in tok.findall(t)]
        df.update(set(ws)); bi.update(set(zip(ws, ws[1:])))
    K = {w for w, c in df.items() if c >= 40 and len(w) >= 2} | FW
    gm = {}
    for t, c in df.items():
        if len(t) < 7 or len(t) > 30 or t in PROTECT or c > 600: continue
        best = None
        for i in range(2, len(t) - 1):
            a, b = t[:i], t[i:]
            if a not in K or b not in K: continue
            if len(a) < 3 and a not in FW: continue
            if len(b) < 3 and b not in FW: continue
            if len(a) <= 2 or len(b) <= 2:
                if bi[(a, b)] < 25: continue          # 'in'+'consistently' is a real word; only split when the pair is a common phrase
            elif not (a in FW or b in FW or bi[(a, b)] >= 25): continue
            sc = min(df.get(a, 0), df.get(b, 0))
            if sc < 8 * c: continue
            if best is None or sc > best[0]: best = (sc, a, b)
        if best: gm[t] = (best[1], best[2], c)
    # anchor-prefix glue: a rare token that is a domain word + a frequent word (noticelast, rentfor, leasewithout)
    for t, c in df.items():
        if t in gm or len(t) < 8 or len(t) > 30 or c > 12 or t in PROTECT or t in REAL_WORDS: continue
        for anc in ANCHORS:
            if t.startswith(anc) and len(t) - len(anc) >= 3 and t[len(anc):] in K and df.get(t[len(anc):], 0) >= 40:
                gm[t] = (anc, t[len(anc):], c); break
    return gm

def pre_glue(t):
    """character-level glue repair: lightsBreaker, removeTRAO, problem.What, eviction01"""
    t = re.sub(r'(?<=[a-z]{3})(?=[A-Z][a-z]{2,})', ' ', t)
    t = re.sub(r'(?<=[a-z]{3})(?=[A-Z]{2,}\b)', ' ', t)
    t = re.sub(r'(?<=[a-z]{2})([.!?;:])(?=[A-Z])', r'\1 ', t)
    t = re.sub(r'(?<=[A-Za-z]{4})(?=\d)', ' ', t)
    return t

def apply_glue(text, gm):
    text = pre_glue(text)
    def rep(m):
        w = m.group(0); lw = w.lower()
        if lw in gm:
            a, b, _ = gm[lw]
            return w[:len(a)] + ' ' + w[len(a):]
        return w
    return re.sub(r"[A-Za-z]{7,30}", rep, text)

# ---- sentences / negation
SEP = re.compile(r"(?<=[.!?;:])\s+|\s+-{2,}\s*|\s*\*{2,}\s*|\s+/\s+|\s+\|\s+")
def segments(text):
    segs = []; pos = 0
    for m in SEP.finditer(text):
        if m.start() > pos: segs.append((pos, m.start()))
        pos = m.end()
    if pos < len(text): segs.append((pos, len(text)))
    return segs

NEG_BEFORE = re.compile(r"\b(?:no|not|never|without|zero|nor|none|free\s+of|isn't|aren't|wasn't|weren't|doesn't|don't|didn't|hasn't|haven't|denies|denied|nothing)\s+(?:(?:any|visible|current|more|further|active|noticeable|apparent|obvious|real|actual|longer|evidence\s+of|signs?\s+of|traces?\s+of|a|an|the|of|major|other|new|sign)\s+){0,3}$", re.I)
def negated(text, start, seg_start):
    pre = text[max(seg_start, start - 45):start]
    return bool(NEG_BEFORE.search(pre))


# ====================================================================================================
# RULES
# ====================================================================================================
import re

# ------------------------------------------------------------------ misspelling-tolerant fragments (every variant below occurs in the records)
LANDLORD = r"(?:landlord|lanlord|landord|lanldord|landloard|landlored|landlard)"
CEIL = r"(?:ceilings?|cieling|celing|celling)"
ELECTRICAL = r"(?:electrical|eletrical|electical|electrial)"
ELECTRICITY = r"(?:electricity|electricty|eletricity|electicity|elctricity)"
FURNACE = r"(?:furnace|furnance)"
PLUMBING = r"(?:plumbing|pluming|plumbng)"
TOILET = r"(?:toilet|toliet|tolet)"
INFEST = r"(?:infest\w*|infestion|investation|infestatin)"
COCKROACH = r"(?:cock|coc|cok|coch)?roach(?:es)?|cochroach|cockroches|cokroaches"
UNHAB = r"uninhabitable|inhabitable|un[- ]?inhabitable|non[- ]?habitable|un[- ]?habitable|unihabitable|unhabitable|not\s+habitable"
HARASS = r"harr?ass\w*"
RETAL = r"retaliat\w*|retalit\w*|retailiat\w*|relatliation"
EVICTION = r"(?:eviction|eviciton|evction|evection|eveiction)"
MAINT = r"(?:maintenance|maintenace|maintence|maintenence|maintanence|maintainance|maintance|mainenance)"
INOP = r"(?:inoperable|innoperable|inoperative|inop)"
VENTIL = r"(?:ventilation|ventillation|ventalation)"

# ------------------------------------------------------------------ cue building blocks
NT = r"(?:n't|\bnot\b|\bnever\b|\bno\s+longer\b|\bcannot\b|\bcan\s+not\b|\bunable\s+to\b|\b(?:dont|doesnt|wont|cant|isnt|hasnt|havent|didnt|wasnt)\b)"
FUNC = r"(?:work(?:ing|ed|s)?|function\w*|operat\w+|properly|turn(?:ed|ing)?\s+(?:on|up)|open\w*|clos\w+|lock\w*|latch\w*|flush\w*|drain\w*|heat\w*|stay\w*|hold\w*|get(?:ting)?\s+(?:hot|warm|cold|any)|com(?:e|es|ing)\s+on|start\w*|run(?:ning)?|reach\w*|vent(?:ing)?\w*|seal\w*|us(?:e|ing))"
CUE_NOTWORK = NT + r"\s+(?:been\s+|really\s+|even\s+|properly\s+|currently\s+|fully\s+|able\s+to\s+|be\s+|all\s+|always\s+|entirely\s+|completely\s+|consistently\s+|reliably\s+|still\s+|yet\s+)?" + FUNC
CUE_UNFIXED = r"\bnot\s+(?:been\s+)?(?:addressed|fixed|repaired|resolved|replaced|serviced|handled|taken\s+care\s+of)\b|\bunaddressed\b|\bunrepaired\b|\bunresolved\b"
CUE_CODE = r"\bout\s+of\s+compliance\b|\bnon[- ]?complian\w*\b|\bnot\s+(?:in\s+)?complian\w*\b|\bnot\s+up\s+to\s+code\b|\bcode\s+violation\w*\b"
CUE_BROKEN = r"\b(?:broken|broke|busted|" + INOP + r"|out\s+of\s+(?:order|service|commission)|defective|faulty|malfunction\w*|damaged|dead|failed|failing|failure|fail(?:s)?|stopped|cracked|shattered|torn|missing|stuck|jammed|clogged|leaking|leaks?|loose|collapsed|burn(?:ed|t)\s+out|blown|fried|unsafe|hazardous|dangerous|disrepair|worn|lost|unavailable|inaccessible|spray\w*|danger|dislodg\w*|dislocat\w*|detach\w*|disconnect\w*|came\s+off|fell\s+off|hanging|dangling|improperly|incorrectly|tip\s+over|lacks?|lacking|not\s+installed)\b"
CUE_OUT = r"\b(?:is|are|was|were|been|being|has\s+been|have\s+been|went|goes|gone|keeps?\s+going|remains?)\s+(?:completely\s+|totally\s+|still\s+|been\s+)?(?:out|off|down|dead|cold|gone|shut[\s-]*off|turned\s+off|disconnected)\b|\b(?:out|off)\s+(?:for|since)\b|\b(?:turned|shut|cut|switched)[\s-]*off\b"
CUE_ABSENT = r"\b(?:no|without|lack\s+of|loss\s+of|none|zero|missing)\b"
CUE_INADEQ = r"\b(?:inadequate|insufficient|poor|barely|intermittent\w*|inconsistent\w*|unreliable|weak|low|slow|not\s+enough|lukewarm|tepid|freezing|icy)\b"
CUE_PROBLEM = r"\b(?:problems?|issues?|trouble|concerns?|repair(?:s|ed|ing)?|fix(?:ed|es|ing)?|replace\w*|not\s+fixed|unfixed)\b"
STRONG_FAIL = "|".join([CUE_NOTWORK, CUE_UNFIXED, CUE_CODE, CUE_BROKEN, CUE_OUT, CUE_ABSENT, CUE_INADEQ])
# "no X" / "without X" / "doesn't have X" prefix used by the strong absence rules
NOPFX = r"(?:no|without|lack\s+of|loss\s+of|lost|zero|(?:ha(?:s|ve|d)|do(?:es)?|did)n't\s+(?:have\s+|had\s+|got\s+|get\s+)?|(?:ha(?:s|ve|d)|do(?:es)?|did)\s+not\s+(?:have\s+|had\s+|got\s+|get\s+)?)"
# adjectives that sit in front of the noun they describe ("busted dishwasher") - they bind to the NEXT object, not the previous one
PRENOM_ADJ = {'broken', 'busted', 'defective', 'faulty', 'damaged', 'dead', 'cracked', 'shattered', 'torn', 'missing', 'stuck', 'jammed', 'clogged', 'loose', 'worn', 'rotted', 'rotten', 'leaking', 'blown', 'fried', 'inoperable', 'inoperative', 'old', 'lost', 'unavailable'}

def rx(p, flags=re.I): return re.compile(p, flags)

class Rule:
    def __init__(s, id, lane, cat, kind, pat, cue=None, cue2=None, win=60, nwin=24, reject=None, neg=False, prio=20,
                 note='', pre_reject=None, weak_alone=False, desc='', sev=False, group=None):
        s.id, s.lane, s.cat, s.kind = id, lane, cat, kind
        s.rx = rx(pat); s.cue = rx(cue) if cue else None; s.cue2 = rx(cue2) if cue2 else None
        s.win = win; s.nwin = nwin
        s.reject = rx(reject) if reject else None
        s.neg = neg; s.prio = prio; s.note = note; s.weak_alone = weak_alone
        s.pre_reject = rx(pre_reject) if pre_reject else None
        s.pat = pat; s.cue_pat = cue; s.cue2_pat = cue2; s.desc = desc; s.sev = sev; s.group = group

RULES = []
def R(*a, **k):
    r = Rule(*a, **k); RULES.append(r); return r

# ======================================================================= HABITABILITY  (landlord-tenant issue AND an SDCI code issue)
H = 'HAB'
# ---- HEAT
R('HEAT-01', H, 'HEAT', 'STRONG', r"\b" + NOPFX + r"\s*(?:any\s+|working\s+|adequate\s+|proper\s+|central\s+|real\s+|consistent\s+)?(?:heat(?:ing)?|heaters?|" + FURNACE + r"|boiler|radiators?)\b(?!\s+(?:pump|wave|advisory))", prio=10,
  desc="'no heat', 'without heating', 'doesn't have a furnace'")
R('HEAT-02', H, 'HEAT', 'STRONG', r"\b(?:defective|faulty|broken|" + INOP + r"|inadequate|insufficient|malfunctioning|failed|failing|non[- ]?working|bad|old)\s+(?:central\s+|electric\s+|gas\s+|baseboard\s+|wall\s+|space\s+)?(?:heat(?:ing)?(?:\s+system|\s+unit)?|heaters?|" + FURNACE + r"|boiler|radiators?|thermostat)\b", prio=10, pre_reject=r"water\s+$",
  desc="'defective heating system', 'broken heater', 'inadequate heat'")
R('HEAT-03', H, 'HEAT', 'COMPOUND', r"\b(?:heat(?:ing)?(?:\s+(?:system|unit|source))?|heaters?|" + FURNACE + r"|boiler|radiators?|baseboards?(?:\s+heat\w*)?|thermostat|steam)\b",
  cue=STRONG_FAIL + r"|\b(?:cold|freezing|too\s+hot|degrees|temperature)\b", cue2=CUE_PROBLEM, win=80,
  reject=r"\b(?:heat\s+pump|heat\s+wave|heat\s+advisory|heat\s+stroke|heat\s+exhaustion)\b", pre_reject=r"(?:water|hot\s+water)\s+$", weak_alone=True, prio=20,
  desc="heat / heater / furnace / boiler / radiator / thermostat + a failure word in the same clause ('heat has not been working'); object alone = borderline")
R('HEAT-04', H, 'HEAT', 'STRONG', r"\b(?:freezing|ice[- ]cold|very\s+cold|extremely\s+cold|too\s+cold|so\s+cold)\s+(?:in\s+(?:the\s+|my\s+|our\s+)?)?(?:apartment|unit|home|house|bedroom|building|rooms?|inside)\b|\b(?:apartment|unit|house|home|building|rooms?)\s+(?:is|are|was|were|stays?|gets?|remains?)\s+(?:freezing|ice[- ]cold|very\s+cold|extremely\s+cold|too\s+cold|so\s+cold)\b", prio=15,
  desc="inference: 'the apartment is freezing' (cold unit, heat not named)")

# ---- HOT WATER
R('HW-01', H, 'HOT_WATER', 'STRONG', r"\b" + NOPFX + r"\s*(?:any\s+|running\s+|consistent\s+|adequate\s+|reliable\s+|enough\s+)?(?:hot|warm)\s*[- ]?\s*water\b", prio=10,
  desc="'no hot water', 'without warm water', 'hasn't had hot water'")
R('HW-02', H, 'HOT_WATER', 'COMPOUND', r"\b(?:hot|warm)\s*[- ]?\s*water(?:\s+heater)?\b|\bwater\s+heaters?\b|\bhot\s+water\s+tank\b",
  cue=STRONG_FAIL + r"|\b(?:runs?\s+out|goes?\s+cold|turn\w*\s+(?:extremely\s+|very\s+|ice\s+)?cold|only\s+cold|cold\s+water\s+only|rarely\s+(?:even\s+)?(?:gets?|getting)\s+(?:hot|warm)|never\s+(?:gets?|get)\s+(?:hot|warm))\b", cue2=CUE_PROBLEM, win=80, weak_alone=True, prio=20,
  desc="hot water / water heater + a failure word ('hot water is not working', 'water heater leaks')")
R('HW-03', H, 'HOT_WATER', 'COMPOUND', r"\b(?:showers?|baths?|bathtubs?|tub|faucet|taps?|water)\b",
  cue=r"\b(?:ice[- ]cold|lukewarm|tepid|freezing|only\s+cold|cold\s+water\s+only|only\s+(?:have\s+)?cold\s+water|never\s+(?:gets?|get)\s+(?:hot|warm)|comes?\s+out\s+cold|came\s+out\s+cold|turns?\s+cold|goes?\s+cold|barely\s+warm)\b", win=40, prio=25,
  desc="inference: shower/water is lukewarm or cold ('shower came out cold')")

# ---- WATER SERVICE
R('WATER-01', H, 'WATER_SERVICE', 'STRONG', r"\b" + NOPFX + r"\s*(?:any\s+|running\s+|potable\s+|drinking\s+|clean\s+)?water\b(?!\s+(?:damage|heater|leak|bill|meter|pressure))|\bwater\s+(?:service\s+)?(?:has\s+been\s+|was\s+|is\s+|were\s+|got\s+|being\s+)?(?:shut[\s-]*(?:off|down)|turned\s+off|cut\s+off|disconnected|off\b)", prio=10,
  reject=r"\b(?:trees?|plants?|lawn|garden|vegetation|landscap\w*|shrubs?|grass)\b", desc="'no running water', 'water has been off', 'water shut off'")
R('WATER-02', H, 'WATER_SERVICE', 'STRONG', r"\b(?:low|no|poor|weak|little|bad|zero|insufficient|inadequate)\s+(?:water\s+)?pressure\b|\bwater\s+pressure\s+(?:is\s+|was\s+)?(?:low|weak|poor|bad|non-?existent|terrible)\b", prio=10, desc="low / no water pressure")
R('WATER-03', H, 'WATER_SERVICE', 'STRONG', r"\b(?:brown|yellow|rusty|discolou?red|murky|dirty|cloudy|orange|black|smelly|contaminated)\s+(?:tap\s+|drinking\s+)?water\b|\bwater\s+(?:is|was|looks?|comes?\s+out|came\s+out)\s+(?:\w+\s+)?(?:brown|yellow|rusty|discolou?red|murky|dirty|cloudy|orange|black)\b|\b(?:poor|bad|low)\s+water\s+quality\b|\bsediment\s+in\s+(?:the\s+)?water\b", prio=10, desc="brown / yellow / rusty / dirty water, poor water quality")
R('UTIL-01', H, 'WATER_SERVICE', 'STRONG', r"\bwater\b(?:\s*(?:,|and|&|or|/)\s*(?:gas|power|electricity|heat|water))*\s+(?:(?:has|have|had|was|were|is|are|just|been|being|got|also|now)\s+)*(?:shut[\s-]*(?:off|down)|turned\s+off|cut\s+off|disconnected|terminated)\b", prio=10,
  reject=r"\b(?:trees?|plants?|lawn|garden|vegetation)\b", desc="'water and gas shut off' (service cut-off, water named)", group='UTIL')
R('UTIL-02', H, 'ELECTRICAL', 'STRONG', r"\b(?:power|electricity|electric)\b(?:\s*(?:,|and|&|or|/)\s*(?:gas|water|heat|power|electricity))*\s+(?:(?:has|have|had|was|were|is|are|just|been|being|got|also|now)\s+)*(?:shut[\s-]*(?:off|down)|turned\s+off|cut\s+off|disconnected|terminated)\b", prio=10, desc="'power shut off' / 'electricity disconnected'", group='UTIL')
R('UTIL-03', H, 'UTILITY_SERVICE_LOSS', 'STRONG', r"\b(?:gas|utilities|utility\s+service)\b(?:\s*(?:,|and|&|or|/)\s*(?:gas|water|heat|power|electricity))*\s+(?:(?:has|have|had|was|were|is|are|just|been|being|got|also|now)\s+)*(?:shut[\s-]*(?:off|down)|turned\s+off|cut\s+off|disconnected|terminated)\b|\bgas\s+(?:shut[\s-]*off|shutoff)\b|\bgas\s+(?:has\s+been\s+|is\s+|was\s+)?(?:out|off)\b|\bgas\s+outage\b", prio=12, desc="gas / utilities shut off or out (no heat or cooking gas)", group='UTIL')
# ---- LEAKS / WATER INTRUSION
R('LEAK-01', H, 'LEAKS_WATER_INTRUSION', 'STRONG', r"\bwater\s+(?:damage[d]?|intrusion|infiltration|stains?|coming\s+(?:in|through|down|into|from)|pouring|dripping|seeping|running\s+down|getting\s+in|entering|leaking)\b|\bwater\s+(?:coming|dripping|leaking|pouring|running|seeping)\s+(?:from|out\s+of)\b|\b(?:water|rain)\s+(?:comes?|came|gets?|got)\s+(?:in|into|through)\b|\bwet\s+(?:walls?|carpet|floors?|ceilings?|basement|insulation|drywall)\b|\bstanding\s+water\b|\bpooling\s+water\b|\b(?:flood(?:ed|ing|s)?|inundat\w+)\b|\bwater\s+in\s+(?:the\s+|my\s+|our\s+)?(?:basement|garage|unit|apartment|wall|walls|ceiling|bedroom|bathroom|kitchen|living\s+room|crawl\s*space)\b", prio=10, reject=r"\b(?:flood\s+(?:zone|plain|insurance|map)|storm\s+drain)\b",
  desc="water damage, flooding, water coming in / through / from the ceiling, standing water")
R('LEAK-02', H, 'LEAKS_WATER_INTRUSION', 'STRONG', r"\b(?:roof|" + CEIL + r"|window|windows|wall|walls|skylight|balcony|deck|basement|garage|attic|foundation|floor)\s+(?:is\s+|are\s+|has\s+been\s+|keeps?\s+)?(?:leak\w*|dripp?\w*|seep\w*)\b|\b(?:leak\w*|dripp?\w*)\s+(?:roof|" + CEIL + r"|window|windows|wall|walls|skylight|balcony|basement|garage|attic)\b|\b(?:roof|" + CEIL + r"|window|wall|basement|skylight|deck)\s+leaks?\b|\bleak(?:s|ing)?\s+(?:from|in|into|through|above|below|behind)\s+(?:the\s+|my\s+|our\s+|a\s+)?(?:roof|" + CEIL + r"|window|windows|wall|walls|skylight|balcony|deck|basement|garage|attic|unit\s+above|apartment\s+above|upstairs|floor)\b", prio=8,
  desc="'leaking roof', 'ceiling leaks', 'leak through the wall'")
R('LEAK-03', H, 'LEAKS_WATER_INTRUSION', 'PRESENCE', r"\b(?:leak(?:s|ed|ing|y)?|dripp?(?:s|ing|ed)?|seep(?:s|ing|ed|age)?)\b", prio=40,
  reject=r"\bgas\s+leak|\bleak(?:s|ing)?\s+(?:of\s+)?gas\b|\bsewage\s+leak|\bleak(?:s|ing)?\s+(?:from\s+)?(?:the\s+|a\s+)?(?:" + TOILET + r"|sink|faucet|tub|shower|pipes?|drain|water\s+heater|radiator|dishwasher|washer)|\b(?:" + TOILET + r"|sink|faucet|tub|shower|pipes?|drain|water\s+heater|radiator|dishwasher|washer)s?\s+(?:is\s+|are\s+)?(?:leak|dripp?)|\b(?:oil|fluid|refrigerant)\s+leak|\bleak\s+detect|\bdrip\s+(?:irrigation|edge)\b",
  desc="bare 'leak / leaking / dripping' not tied to a fixture (fixture leaks go to plumbing)")
R('LEAK-04', H, 'LEAKS_WATER_INTRUSION', 'COMPOUND', r"\bwhen\s+it\s+rain(?:s|ed)?\b|\bduring\s+(?:the\s+)?rain(?:s|storms?)?\b|\bin\s+(?:the\s+)?rain\b", cue=r"\b(?:water|leak\w*|drip\w*|wet|flood\w*|damp|seep\w*|soak\w*|puddle\w*|pour\w*|comes?\s+in|coming\s+in)\b", win=70, prio=20,
  desc="inference: water problem 'when it rains'")
R('LEAK-05', H, 'LEAKS_WATER_INTRUSION', 'STRONG', r"\bnot\s+(?:water|weather)[- ]?tight\b|\bnot\s+weather[- ]?proof\w*\b|\bdrafty\b|\bdrafts?\b", prio=30, note='building envelope', desc="not watertight / weatherproof, drafty windows")

# ---- PLUMBING / SEWAGE
R('PLUMB-01', H, 'PLUMBING_SEWAGE', 'PRESENCE', r"\b(?:raw\s+)?sewage\b|\bsewer\s+(?:line|main|gas|smell|odou?r|back[- ]?up|pipe|system|lateral|cleanout)s?\b|\bseptic\b", prio=10, desc="sewage, raw sewage, sewer line / smell / backup, septic")
R('PLUMB-02', H, 'PLUMBING_SEWAGE', 'STRONG', r"\b(?:back(?:ed|ing|s)?[- ]?(?:up|ups)|backups?|clog(?:ged|ging|s)?|plugged\s+(?:up|" + TOILET + r"|drain|sink)|blocked\s+(?:drain|" + TOILET + r"|sink|pipe|line|tub|shower)s?)\b", prio=15, reject=r"\bbacked\s+up\s+(?:by|with|against)\b|\bback[- ]?up\s+(?:generator|power|plan|copy|key|battery)\b|\bbackup\s+(?:generator|power|plan|copy|key|battery)\b|\bper\s+tech\b",
  desc="backed up / clogged / blocked drain, toilet or sewer")
R('PLUMB-03', H, 'PLUMBING_SEWAGE', 'STRONG', r"\b(?:burst|broken|busted|cracked|frozen|corroded|rusted)\s+(?:water\s+|sewer\s+|main\s+)?(?:pipes?|lines?|mains?)\b|\bpipes?\s+(?:burst|broke|broken|froze|frozen|bust\w*|leak\w*)\b|\bpipe\s+burst\b|\bwater\s+(?:main|line)\s+(?:break|broke|burst|leak\w*)\b", prio=8, desc="burst / broken pipe, water main break")
R('PLUMB-04', H, 'PLUMBING_SEWAGE', 'COMPOUND', r"\b(?:" + TOILET + r"s?|sinks?|bath\s*tubs?|tubs?|showers?|faucets?|taps?|drains?|pipes?|piping|" + PLUMBING + r"|water\s+lines?|garbage\s+disposal|sump\s*pumps?)\b",
  cue=STRONG_FAIL + r"|\b(?:leak\w*|clog\w*|backed|overflow\w*|burst|running|keeps?\s+running|slow|gurgl\w*|smell\w*|rust\w*|corrod\w*|spray\w*)\b", cue2=CUE_PROBLEM, win=70, prio=12,
  reject=r"\b(?:storm\s+drain|shower\s+curtain|" + TOILET + r"\s+paper|sink\s+hole)\b", desc="toilet / sink / tub / shower / faucet / drain / pipe / sump pump + a failure word ('toilet is leaking')")
R('PLUMB-05', H, 'PLUMBING_SEWAGE', 'COMPOUND', r"\boverflow(?:ed|ing|s)?\b", cue=r"\b(?:" + TOILET + r"s?|sinks?|tubs?|bath\w*|showers?|drains?|sewer|sewage|pipes?|wastewater|gutters?)\b", win=40, prio=14, desc="'overflowing toilet / sink / drain'")

# ---- MOLD / MOISTURE
R('MOLD-01', H, 'MOLD_MOISTURE', 'PRESENCE', r"\b(?:mold|mould|moldy|mouldy|molds|mildew\w*|fungus|fungal|spores?)\b", prio=10, desc="mold, moldy, mildew, fungus, spores")
R('MOLD-02', H, 'MOLD_MOISTURE', 'PRESENCE', r"\b(?:moisture|condensation|dampness|damp|humidity|humid|mustiness|musty)\b", prio=20, desc="moisture, condensation, damp, musty")

# ---- PESTS
R('PEST-01', H, 'PESTS', 'PRESENCE', r"\bbed\s*-?\s*bugs?\b|\b(?:" + COCKROACH + r")\b|\b(?:rats?|mice|mouse|rodents?|vermin|raccoons?|squirrels?|possums?|skunks?)\b|\b(?:ants?|termites?|fleas?|lice|mites?|wasps?|hornets?|bees?|spiders?|maggots?|gnats?|moths?|silverfish|earwigs?|bugs?|insects?|pests?|critters?|flies|ticks?)\b", prio=10,
  desc="bed bugs, roaches, rats, mice, rodents, ants, fleas, bugs, pests (negated mentions rejected)")
R('PEST-02', H, 'PESTS', 'PRESENCE', r"\b(?:" + INFEST + r"|exterminat\w*|fumigat\w*|droppings)\b", prio=15, desc="infestation / infested, exterminator, fumigation, droppings")
R('PEST-03', H, 'PESTS', 'COMPOUND', r"\b(?:bites?|bitten|welts?)\b", cue=r"\b(?:bugs?|bed|insects?|spiders?|fleas?|mites?|ants?|itch\w*|rash\w*)\b", win=40, prio=30, desc="bites / welts next to bug words")

# ---- ELECTRICAL
R('ELEC-01', H, 'ELECTRICAL', 'STRONG', r"\b" + NOPFX + r"\s*(?:any\s+)?(?:electric(?:al)?(?:\s+service)?|" + ELECTRICITY + r"|power)\b|\b(?:power|" + ELECTRICITY + r")\s+(?:is\s+|was\s+|has\s+been\s+|keeps?\s+|being\s+)?(?:out|off|going\s+out|goes?\s+out|cut\s+off|shut[\s-]*(?:off|down)|disconnected)\b|\b(?:power|" + ELECTRICITY + r"|electric)\s+(?:outages?|failure|surge)s?\b|\b(?:" + ELECTRICITY + r"|power)\s+(?:was\s+|being\s+|got\s+)?(?:shut|turned|cut)\s+off\b|\bblackout\b", prio=10,
  desc="no power / electricity out / power outage")
R('ELEC-02', H, 'ELECTRICAL', 'STRONG', r"\bexposed\s+(?:electrical\s+)?(?:wires?|wiring|conductors?|cables?)\b|\b(?:live|bare|frayed|hanging|dangling)\s+(?:electrical\s+)?wires?\b|\bspark(?:s|ing|ed)\b|\barcing\b|\bshort(?:ed|ing|s)?\s+(?:out|circuit)\b|\bshorts?\s+out\b|\belectrocut\w*\b|\belectric(?:al)?\s+shock\w*\b|\bshock(?:ed)?\s+(?:me|us|my|by)\b", prio=8, desc="exposed / live wires, sparks, shorts, shocks")
R('ELEC-03', H, 'ELECTRICAL', 'COMPOUND', r"\b(?:outlets?|sockets?|receptacles?|gfci|breakers?|fuse(?:s|\s*box)?|circuit\s+breakers?|circuits?|wiring|wireing|wires?|electrical\s+panel|breaker\s+box|fuse\s+panel|electric(?:al)?\s+meter)\b",
  cue=STRONG_FAIL + r"|\b(?:dead|loose|burn\w*|melt\w*|buzz\w*|crackl\w*|trip\w*|overload\w*|flicker\w*|old|outdated|hazard\w*|fire|ungrounded|knob|exposed)\b", cue2=CUE_PROBLEM, win=55, prio=12,
  desc="outlet / breaker / fuse / wiring / circuit + a failure word ('outlets not working')")
R('ELEC-04', H, 'ELECTRICAL', 'STRONG', r"\b" + ELECTRICAL + r"\s+(?:problems?|issues?|hazards?|work|wiring|system|fire|code|violations?|concerns?|repairs?|failure|outage|safety)\b|\b(?:faulty|bad|old|outdated|unsafe|defective|dangerous|improper|illegal|unpermitted|substandard)\s+(?:" + ELECTRICAL + r"|wiring|wireing)\b|\bwiring\s+(?:problems?|issues?|is|are|was)\b|\bknob\s*(?:and|&)\s*tube\b", prio=15,
  desc="'electrical problems / issues / hazard', 'faulty wiring', knob-and-tube")
R('ELEC-05', H, 'ELECTRICAL', 'COMPOUND', r"\b(?:lights?|light\s+fixtures?|bulbs?|lamps?|lighting)\b",
  cue=r"\b(?:flicker\w*|burn(?:ed|t)\s+out|not\s+work\w*|doesn't\s+work|don't\s+work|dead|out|off|dark|broken|missing|no\s+(?:power|lights?))\b", win=40, prio=30,
  reject=r"\b(?:street\s*light|traffic\s+light|stop\s*light|red\s+light|light\s+rail|city\s+light|seattle\s+city\s+light|light\s+bill|sky\s*light|natural\s+light|light\s+industrial|light\s+and\s+air)\b", pre_reject=r"(?:street|traffic|stop|red|city|natural|day)\s*$",
  desc="lights / fixtures / bulbs + 'flicker', 'out', 'not working'")

# ---- STRUCTURAL
R('STRUCT-01', H, 'STRUCTURAL', 'PRESENCE', r"\b(?:collaps(?:e|ed|ing)(?!\s+(?:sewer|pipe|drain|water|main|line|septic))|sagging|sagged|buckl(?:ed|ing)|bulging|bowing|bowed|crumbl(?:ed|ing)|falling\s+(?:apart|down|in|off)|fell\s+(?:down|off|in)|caving\s+in|cave[- ]?in|rott(?:ed|ing|en)|dry\s*rot|dilapidated|deteriorat\w+|disrepair|structural(?:ly)?|foundation\s+(?:problems?|issues?|damage|cracks?|settling|sinking|failure))\b", prio=10,
  desc="collapse, sagging, bulging, rotting, falling apart, deteriorated, disrepair, structural, foundation problems")
R('STRUCT-02', H, 'STRUCTURAL', 'STRONG', r"\bholes?\s+in\s+(?:the\s+|my\s+|our\s+|a\s+)?(?:wall|walls|" + CEIL + r"|floor|roof|siding|door|window|stairs?|deck|porch|foundation|basement|bathroom|kitchen|bedroom|unit|apartment|building)\b|\b(?:wall|" + CEIL + r"|floor|roof)\s+(?:has\s+)?(?:a\s+)?holes?\b|\bgaping\s+hole\b|\bmissing\s+(?:drywall|siding|shingles|stairs?|steps?|railing|floor|floorboards?|tiles?|plaster|" + CEIL + r"|stair\s+treads?|handrail)\b|\bdrywall\s+(?:missing|damage\w*|falling)\b|\bno\s+(?:hand\s*)?rail(?:ing)?s?\b|\bholes?\s+(?:where|that)\s+(?:rats?|mice|rodents?|pests?)", prio=8,
  desc="'hole in the ceiling / wall / floor', missing drywall / railing / stairs")
R('STRUCT-03', H, 'STRUCTURAL', 'COMPOUND', r"\b(?:foundation|roof|" + CEIL + r"|walls?|floors?|flooring|subfloor|stairs?|stairway|stairwell|steps?|railings?|hand\s*rails?|banister|porch|deck|balcony|siding|drywall|plaster|insulation|chimney|garage|fence|beams?|joists?|studs?|crawl\s*space|attic)\b",
  cue=r"\b(?:holes?|crack(?:s|ed|ing)?|rott\w*|sagging|collaps\w*|falling|fell|loose|broken|unsafe|unstable|dangerous|deteriorat\w*|crumbl\w*|bulg\w*|buckl\w*|uneven|sinking|leaning|peeling|bowed|detached|wobbl\w*|shaky|giving\s+way|structurally|not\s+(?:safe|secure|stable|level|up\s+to\s+code)|exposed|damage[d]?)\b", cue2=CUE_PROBLEM, win=45, prio=30,
  reject=r"\b(?:sidewalk|street|road|alley|curb|parking\s+(?:lot|garage))\b", desc="roof / ceiling / wall / floor / stairs / porch / deck / railing + a damage word")
R('STRUCT-04', H, 'STRUCTURAL', 'COMPOUND', r"\b(?:cracks?|cracked|cracking)\b", cue=r"\b(?:walls?|" + CEIL + r"|foundation|floors?|siding|plaster|drywall|stairs?|concrete|brick|stucco|windows?)\b", win=40, prio=30, desc="'cracks in the wall / foundation / window'")

# ---- DOORS / WINDOWS / LOCKS / SECURITY / ACCESS SYSTEMS
R('DOOR-01', H, 'DOORS_WINDOWS_SECURITY', 'STRONG', r"\b(?:broken|busted|cracked|shattered|missing|stuck|jammed|damaged|rotted|rotten|boarded[- ]up|painted[- ]shut)\s+(?:front\s+|back\s+|entry\s+|bedroom\s+|bathroom\s+|sliding\s+|glass\s+|exterior\s+|apartment\s+|unit\s+)?(?:doors?|windows?|locks?|deadbolts?|latch\w*|screens?|door\s*frames?|window\s*frames?|gates?)\b|\b(?:doors?|windows?|locks?|deadbolts?|latch\w*|screens?|gates?)\s+(?:is\s+|are\s+|was\s+|were\s+|has\s+been\s+|have\s+been\s+)?(?:broken|busted|cracked|shattered|missing|stuck|jammed|damaged|rotted|loose|painted\s+shut)\b|\b(?:can't|cannot|can\s+not|unable\s+to)\s+(?:lock|close|open|secure)\s+(?:the\s+|my\s+|our\s+|her\s+|his\s+|their\s+|a\s+)?(?:door|window|unit|apartment|gate)s?\b|\bno\s+(?:working\s+)?(?:lock|deadbolt|latch)\b|\bunsecured\b|\b(?:doesn't|won't|does\s+not|will\s+not|not)\s+lock(?:ing)?\b|\b(?:doors?|windows?)\s+(?:won't|doesn't|don't|do\s+not|does\s+not|will\s+not|not|cannot|can\s+not)\s+(?:be\s+)?(?:close|closed|open|opened|shut|latch|seal)\b", prio=10,
  desc="broken / stuck window, door, lock, latch; 'doesn't lock'; 'unsecured'")
R('DOOR-02', H, 'DOORS_WINDOWS_SECURITY', 'WEAK', r"\b(?:break[- ]?ins?|broke\s+into|burglar\w*|trespass\w*|squatters?|intruders?)\b", prio=40, note='security / crime context', desc="break-in / squatters / trespass (could be crime rather than a housing defect)")
R('DOOR-03', H, 'DOORS_WINDOWS_SECURITY', 'COMPOUND', r"\b(?:call\s*box|callbox|intercom|buzzer|mail\s*box(?:es)?|mail\s*room|key\s*fobs?|fobs?|garage\s+door|entry\s+system|door\s*bell|door\s*knob)\b", cue=STRONG_FAIL + r"|\b(?:vandaliz\w*|stolen|locked)\b", cue2=CUE_PROBLEM, win=50, prio=30,
  desc="call box / intercom / buzzer / mailbox / key fob / garage door + a failure word")
R('DOOR-04', H, 'DOORS_WINDOWS_SECURITY', 'STRONG', r"\b(?:can't|cannot|can\s+not|unable\s+to|not\s+able\s+to|no\s+longer)\s+(?:receive|get)\s+(?:my\s+|our\s+|any\s+)?mail\b|\b(?:refus\w+|won't|will\s+not|failed|fail\w*|unwilling|asked|ask\w*|request\w*|need\w*|want\w*)\s+(?:to\s+)?(?:re-?key|chang\w+)\s+(?:the\s+|my\s+|our\s+)?locks?\b", prio=12,
  desc="cannot receive mail; landlord will not re-key / change the locks (security request, not a lockout)")

R('DOOR-05', H, 'DOORS_WINDOWS_SECURITY', 'COMPOUND', r"\b(?:doors?|windows?|screens?|gates?|sliding\s+glass)\b",
  cue=r"\b(?:(?:won't|don't|doesn't|do\s+not|does\s+not|will\s+not|can't|cannot|can\s+not|not|unable\s+to)\s+(?:be\s+)?(?:close[d]?|open(?:ed)?|lock(?:ed)?|shut|latch(?:ed)?|seal(?:ed)?|stay\s+(?:closed|shut|open))|cracked|shattered|rotted|rotten|painted\s+shut|off\s+(?:its\s+)?hinges|not\s+secure|unlocked|removed\s+latch|gaps?|drafty|missing\s+(?:glass|screen|lock|latch))\b", win=50, prio=18,
  reject=r"\b(?:next\s+door|door\s+to\s+door|out\s+door|open\s+house)\b", desc="door / window / screen + 'won't close', 'doesn't lock', 'painted shut', 'cracked', 'gap'")
R('HVAC-01', H, 'HVAC_COOLING', 'COMPOUND', r"\b(?:hvac|air[- ]?conditioning|a/c|air\s+conditioner|ac\s+unit)\b", cue=STRONG_FAIL, cue2=CUE_PROBLEM, win=60, prio=22, desc="HVAC / air conditioning + a failure word (cooling is not a code-required service; counted apart from heat)")

# ---- FIRE / SMOKE / CO / GAS
R('FIRE-01', H, 'FIRE_SMOKE_CO_GAS', 'STRONG', r"\b(?:no|missing|without|lack\s+of|broken|dead|expired)\s+(?:working\s+|functioning\s+|operable\s+)?(?:smoke|fire|carbon\s+monoxide|co|c\.o\.)\s*(?:detectors?|alarms?)\b|\b(?:smoke|fire|carbon\s+monoxide|co)\s*(?:detectors?|alarms?)\s+(?:is\s+|are\s+|was\s+|were\s+|has\s+|have\s+)?(?:not|n't|missing|broken|dead|beeping|chirping|removed|disconnected|disabled|" + INOP + r"|expired|never)\b|\b(?:smoke|co|fire)\s*(?:detectors?|alarms?)\s+(?:don't|doesn't|do\s+not|does\s+not|won't)\b|\b(?:beeping|chirping)\s+(?:smoke|alarm|detector)", prio=8,
  desc="no / missing / dead smoke or CO detector, 'smoke detector does not work', chirping alarm")
R('FIRE-02', H, 'FIRE_SMOKE_CO_GAS', 'PRESENCE', r"\bcarbon\s+monoxide\b|\bmonoxide\b", prio=20, desc="carbon monoxide")
R('FIRE-03', H, 'FIRE_SMOKE_CO_GAS', 'STRONG', r"\bgas\s+(?:leak\w*|smell|odou?r|line\s+(?:leak|broken)|pipe\s+(?:leak|broken)|explosion)\b|\bsmell\w*\s+(?:of\s+|like\s+)?gas\b|\bleak(?:s|ing|ed)?\s+(?:natural\s+)?gas\b|\bnatural\s+gas\s+(?:leak|smell)\b|\bpropane\s+leak\b", prio=5, desc="gas leak / smell of gas")
R('FIRE-04', H, 'FIRE_SMOKE_CO_GAS', 'STRONG', r"\bfire\s+(?:hazards?|danger|trap|risk|safety|code|codes|violations?|damage[d]?|escapes?\s+(?:blocked|locked|missing|unsafe)|exits?\s+(?:blocked|locked|missing))\b|\bfire[- ]?trap\b|\belectrical\s+fire\b", prio=10, desc="fire hazard / fire code violation / fire damage / blocked fire escape")
R('FIRE-05', H, 'FIRE_SMOKE_CO_GAS', 'STRONG', r"\b(?:there\s+was|had|has\s+been|after|since|due\s+to|from|following|caused\s+by|resulting\s+from|because\s+of)\s+(?:a\s+|the\s+|an\s+)?(?:building\s+|apartment\s+|unit\s+|kitchen\s+|electrical\s+)?fire\b(?!\s+(?:sprinklers?|alarms?|escapes?|exits?|doors?|department|dept|code|marshal|extinguishers?|safety|hazards?|detectors?|inspections?|station|fighters?|hydrant|lane|trucks?))|\b(?:burned\s+down|burnt\s+down|caught\s+fire|on\s+fire|fire\s+(?:at|broke\s+out|started)|fire\s+in\s+(?:the|a|an|my|our)\s+(?:building|unit|apartment|kitchen)|fire\s+on\s+\d|smoke\s+damage[d]?)\b", prio=12,
  desc="a fire happened: 'caught fire', 'fire in the building', 'displaced due to fire'")
R('FIRE-06', H, 'FIRE_SMOKE_CO_GAS', 'COMPOUND', r"\b(?:egress|fire\s+escapes?|emergency\s+exits?|exits?|fire\s+exits?|fire\s+doors?|sprinklers?|extinguishers?|fire\s+alarm\s+system|stair\s+doors?)\b",
  cue=r"\b(?:blocked|locked|obstruct\w*|no|missing|inadequate|illegal|not|broken|chained|barricaded|unsafe|" + INOP + r"|expired|propped|disabled|doesn't|won't|violation|code|lacks?|lacking)\b", win=45, prio=20,
  reject=r"\b(?:exit\s+(?:interview|strategy|survey|plan)|no\s+exit\s+fee)\b", desc="exit / egress / fire escape / fire door / sprinkler / extinguisher + blocked, missing, broken")
R('FIRE-07', H, 'FIRE_SMOKE_CO_GAS', 'COMPOUND', r"\b(?:smoke\s+(?:detectors?|alarms?)|fire\s+alarms?|alarm\s+system|co2\s+sensors?)\b", cue=CUE_NOTWORK + "|" + CUE_BROKEN + "|" + CUE_ABSENT + "|" + CUE_CODE + "|" + CUE_UNFIXED + r"|\b(?:expired|beeping|chirping|going\s+off|gone\s+off|goes\s+off|went\s+off|set\s+off|false\s+alarms?|error|trouble|fault)\b", cue2=CUE_PROBLEM, win=45, prio=22, weak_alone=True,
  desc="smoke detector / fire alarm + a failure word; object alone = borderline")
R('FIRE-08', H, 'FIRE_SMOKE_CO_GAS', 'WEAK', r"\bburning\s+smell\b|\bsmells?\s+(?:like\s+)?(?:burning|burnt|smoke)\b", prio=40, note='burning smell with no stated source', desc="burning smell with no source named")

# ---- ELEVATOR / ACCESSIBILITY
R('ELEV-01', H, 'ELEVATOR_ACCESS', 'COMPOUND', r"\b(?:elevators?|lifts?)\b", cue=r"\b(?:out|down|broken|not\s+work\w*|doesn't\s+work|stuck|" + INOP + r"|out\s+of\s+(?:order|service)|shut(?:\s+down)?|unsafe|breaks?\s+down|broke\s+down|fail\w*|malfunction\w*|trapped|rescue|repair\w*|closed|problems?|issues?|no\b|without|pit|lost|loss\s+of|unavailable|inaccessible|extended\s+periods?|not\s+(?:blocked|working|functioning|operating)|for\s+(?:over\s+)?(?:\d+|a|several|two|three|four|five|six)\s+(?:day|week|month)s?)\b", win=80, prio=15,
  reject=r"\belevator\s+inspector\b|\belevator\s+(?:permit|certificate|inspection)\b", weak_alone=True, desc="elevator / lift + out, broken, stuck, 'out of service'; elevator alone = borderline")
R('ELEV-02', H, 'ELEVATOR_ACCESS', 'COMPOUND', r"\b(?:ada|wheelchairs?|handicap\w*|accessib\w+|mobility|ramp)\b", cue=r"\b(?:no|not|lack|without|inaccessible|unable|cannot|can't|violation|non[- ]?complian\w*|barrier|blocked|broken|issues?|problems?)\b", win=45, prio=30, desc="ADA / wheelchair / accessibility + a barrier word")

# ---- SANITATION / ODOR
R('SAN-01', H, 'SANITATION_ODOR', 'COMPOUND', r"\b(?:garbage|trash|rubbish|litter|debris|junk|dumpsters?|waste)\b",
  cue=r"\b(?:overflow\w*|piled?|piling|accumulat\w*|strewn|everywhere|spill\w*|uncollected|not\s+(?:collected|picked|removed|emptied)|full|stink\w*|smell\w*|rotting|filth\w*|dumped|dumping|left|abandoned|hallway|stairwell|common|yard|alley|driveway|lobby|basement|laundry|attract\w*|infest\w*|bags?|hoard\w*|sanit\w+|health)\b", win=60, prio=30,
  reject=r"\b(?:garbage\s+disposal|waste\s+of\s+(?:time|money)|solid\s+waste\s+(?:fee|bill|charge)|trash\s+out\s+per)\b", pre_reject=r"(?:garbage\s+)$", desc="garbage / trash / debris / junk + overflowing, piled, smell, hallway")
R('SAN-02', H, 'SANITATION_ODOR', 'PRESENCE', r"\b(?:feces|fecal|poop|excrement|urine|vomit|human\s+waste|dog\s+waste|pet\s+waste|diapers?|filth\w*|unsanitary|insanitary|squalor|squalid|hoard\w*|stench|rancid|putrid)\b", prio=20, desc="feces, urine, vomit, filth, unsanitary, hoarding, stench")
R('SAN-03', H, 'SANITATION_ODOR', 'STRONG', r"\b(?:foul|strong|bad|awful|terrible|horrible|rotten|nasty|chemical|pet|cat|dog|urine|sewage)\s+(?:odou?rs?|smells?|stench)\b|\b(?:stinks?|stinking|stinky|reeks?|reeking)\b", prio=25, desc="foul / strong / awful smell, stinks")
R('SAN-04', H, 'SANITATION_ODOR', 'WEAK', r"\b(?:smell(?:s|ing)?|odou?rs?)\b", prio=60, note='odor with no stated source', desc="'smell' / 'odor' with no source named")

# ---- HAZMAT / AIR
R('HAZ-01', H, 'HAZMAT_AIR', 'PRESENCE', r"\basbestos\b|\blead[- ]?(?:based\s+)?paint\b|\blead\s+(?:dust|exposure|poison\w*|contamination|pipes?)\b|\bfumes?\b|\bmeth(?:amphetamine)?\b|\bair\s+quality\b|\bsecond[- ]?hand\s+smoke\b|\bchemicals?\s+(?:emitted|odou?r|smell|fumes?)\b", prio=15, desc="asbestos, lead paint, fumes, air quality, second-hand smoke")
R('HAZ-02', H, 'HAZMAT_AIR', 'COMPOUND', r"\b(?:" + VENTIL + r"|ventilate\w*|exhaust\s+fans?|bath(?:room)?\s+fans?|fresh\s+air|air\s*flow|vent(?:ing|s)?|flue|chimney|fireplace)\b", cue=r"\b(?:no|lack|poor|inadequate|insufficient|without|not|missing|improper\w*|bad|broken|doesn't|won't|none|blocked|clogged|backdraft\w*|carbon|fumes?)\b", win=45, prio=30, desc="ventilation / exhaust fan / vent / flue + no, poor, blocked")

# ---- OVERCROWDING
R('OCC-01', H, 'OVERCROWDING', 'STRONG', r"\bovercrowd\w*\b|\btoo\s+many\s+(?:people|occupants|tenants|residents)\b|\b(?:\d+|four|five|six|seven|eight)\s+(?:people|persons|adults|tenants)\s+(?:live|living|sleep\w*|in)\s+(?:in\s+)?(?:one|a|the|1)\s+(?:room|bedroom|unit|apartment)\b|\bmaximum\s+occupancy\b|\bexceed\w*\s+(?:the\s+)?(?:maximum\s+)?occupancy\b", prio=20, desc="overcrowding / too many people in the unit / maximum occupancy")

# ---- APPLIANCES / FIXTURES
R('APPL-01', H, 'APPLIANCES_FIXTURES', 'COMPOUND', r"\b(?:stove|oven|burners?|refrigerator|fridge|freezer|dishwasher|microwave|washer|dryer|washing\s+machines?|laundry\s+(?:machines?|room|facilit\w+)|appliances?|cabinets?|counter\s*tops?)\b",
  cue=STRONG_FAIL + r"|\b(?:leak\w*|spark\w*|rust\w*|moldy|dirty|filthy|closed|old)\b", cue2=CUE_PROBLEM, win=70, prio=30, desc="stove / fridge / dishwasher / washer / dryer / laundry + a failure word")

# ---- UNINHABITABLE / SEVERITY
R('SEV-01', H, 'UNINHABITABLE_SEVERITY', 'STRONG', r"\b(?:" + UNHAB + r")\b|\bnot\s+(?:safe|fit|livable|suitable)\s+(?:to\s+live|for\s+habitation|for\s+human)\b|\bunfit\b|\bcondemn\w*\b|\bvacate\s+order\b|\bemergency\s+vacate\b|\bred[- ]?tag\w*\b|\bunlivable\b|\b(?:can't|cannot|couldn't)\s+(?:live|stay|sleep)\s+(?:here|there|in)\b|\bnot\s+habitable\b", prio=10, neg=True, sev=True,
  desc="uninhabitable / unfit / condemned / vacate order / 'can't live here' (severity, not counted as a separate issue)")
R('SEV-02', H, 'UNINHABITABLE_SEVERITY', 'COMPOUND', r"\b(?:had|have|has|forced|need|needed|must)\s+to\s+(?:move(?:\s+out)?|vacate|relocate|evacuate|leave\s+(?:the\s+|their\s+|my\s+|our\s+)?(?:unit|apartment|home|house|building|premises|property))\b", cue=r"\b(?:because|due\s+to|since|after|conditions?|mold|leak\w*|flood\w*|fire|damage|unsafe|hazard\w*|uninhabitable|health|sick)\b", win=80, prio=30, sev=True,
  desc="'had to move out because / due to <condition>' (severity)")
R('HABU-01', H, 'HAB_UNSPECIFIED', 'STRONG', r"\b(?:substandard|sub-standard)\s+(?:rental\s+|living\s+|housing\s+)?(?:housing|conditions?|rental|living|unit|apartment)\b|\b(?:housing|building)\s+(?:code\s+)?violations?\b|\bhbmc\b|\bhousing\s+(?:and\s+building\s+maintenance|code)\b|\bcode\s+violations?\b|\bunsafe\s+(?:conditions?|living)\b|\b(?:health|safety)\s+(?:and|&)\s+(?:safety|health)\b|\bliving\s+conditions\b|\b" + MAINT + r"\s+(?:issues?|problems?|neglect)\b|\bneglect\w*\b|\bdeferred\s+maintenance\b|\bhousing\s+inspection\b|\bno\s+" + MAINT + r"\b|\bhbm\w*\b", prio=50,
  desc="general habitability complaint with no specific defect named ('substandard conditions', 'housing code violations')")

# ======================================================================= PAPERWORK / LANDLORD-TENANT LEGAL  (not an SDCI housing-code defect)
P = 'PAPER'
NDAY = r"(?:\d{1,3}|three|ten|fourteen|twenty|thirty|sixty|ninety)\s*-?\s*days?"
R('EVICT-01', P, 'EVICTION_TERMINATION', 'STRONG', r"\b" + NDAY + r"\s*(?:pay\s+or\s+(?:vacate|quit|leave)|comply\s+or\s+vacate|pov\b|(?:eviction|termination|vacate|quit|move[- ]?out)\s+notice|notice\s+to\s+(?:vacate|quit|terminate|leave|move|end|pay|comply|cure)|notice\s+of\s+(?:termination|eviction|intent)|eviction)\b|\b(?:pay|comply|perform)\s+(?:the\s+rent\s+)?or\s+(?:vacate|quit|leave|move)\b|\bnotice\s+(?:to|of)\s+(?:vacate|quit|terminat\w+|evict\w*|leave|move[- ]?out)\b", prio=8,
  desc="'3 day pay or vacate', '30 day notice to terminate', 'notice to vacate', 'comply or quit'")
R('EVICT-02', P, 'EVICTION_TERMINATION', 'STRONG', r"\b(?:evict(?:ed|ing|s|ion|ions)?|" + EVICTION + r"|unlawful\s+detainer|writ\s+of\s+(?:restitution|eviction)|sheriff)\b", prio=10, desc="eviction / evicted / unlawful detainer / writ / sheriff")
R('EVICT-03', P, 'EVICTION_TERMINATION', 'STRONG', r"\b(?:kick(?:ed|ing)?|throw(?:n|ing)?|threw|put|forc(?:e|ed|ing)|booted|tossed)\s+(?:me|us|him|her|them|the\s+tenants?|tenants?)\s*(?:out|off\s+the\s+property)\b|\b(?:told|ordered|asked|forced|making|made|wants?|trying|attempting)\s+(?:me|us|him|her|them|the\s+tenants?)\s+to\s+(?:leave|vacate|move\s+out|get\s+out)\b|\b(?:told|ordered|asked)\s+to\s+(?:leave|vacate|move\s+out)\b", prio=10,
  desc="everyday wording for being pushed out: 'kicked me out', 'told us to leave', 'asked to move out'")
R('EVICT-04', P, 'EVICTION_TERMINATION', 'STRONG', r"\bterminat(?:e|ed|es|ing|ion)\s+(?:of\s+)?(?:the\s+|my\s+|our\s+|his\s+|her\s+|their\s+)?(?:tenancy|lease|rental(?:\s+agreement)?|agreement|month[- ]to[- ]month)\b|\bnon[- ]?renew\w*|\b(?:not|won't|will\s+not|refus\w+\s+to)\s+renew\w*|\bno[- ]fault\b|\bjust\s+cause\b|\bcause\s+eviction\b|\bnotice\s+to\s+(?:sell|demolish|remodel|renovat\w*)\b", prio=10,
  desc="terminating the tenancy / lease, non-renewal, 'just cause', no-fault")
R('EVICT-05', P, 'EVICTION_TERMINATION', 'COMPOUND', r"\b(?:selling|sale|sold|sell)\b", cue=r"\b(?:notice|vacate|move\s+out|leave|terminate|evict\w*|end\s+(?:the\s+)?(?:lease|tenancy)|tenants?\s+(?:must|have\s+to|need\s+to))\b", win=60, prio=25, desc="property being sold + notice / vacate / move out")
R('EVICT-06', P, 'EVICTION_TERMINATION', 'STRONG', r"\b(?:we|i|tenants?|they|she|he)\s+(?:have|had|need|must|are\s+required|were\s+told)\s+to\s+(?:be\s+)?(?:move[d]?\s+out|out\s+by|vacate)\b|\b(?:daughter|son|family|owner|landlord|relative)\s+(?:to|will|wants?\s+to)\s+move\s+in\b|\bto\s+allow\s+(?:their|his|her|the\s+owner'?s?)\s+\w+\s+to\s+move\s+in\b", prio=10,
  desc="forced move-out wording: 'we have to move out', 'owner's daughter to move in'")
R('RENT-01', P, 'RENT_INCREASE_FEES', 'STRONG', r"\brent\s*(?:increase[sd]?|hike[sd]?|raise[sd]?|surcharge|adjustment)\b|\b(?:raise[sd]?|raising|increase[sd]?|increasing|hik(?:e|ed|ing)|bump(?:ed|ing)?)\s+(?:the\s+|my\s+|our\s+|his\s+|her\s+|their\s+)?(?:monthly\s+)?rent\b|\b(?:rent|monthly\s+rent)\s+(?:went\s+up|is\s+going\s+up|goes\s+up|will\s+(?:go|increase|rise)|was\s+(?:raised|increased)|is\s+being\s+(?:raised|increased)|has\s+(?:increased|been\s+(?:raised|increased))|jump\w*|doubl\w+|tripl\w+|skyrocket\w*)\b|\b(?:rent|rental)\s+(?:is\s+|keeps\s+|continues\s+to\s+)?(?:increas\w+|rais\w+|go\w*\s+up|rising|hiked)\b|\brent\s+(?:control|stabilization)\b|\b(?:increase|hike)\s+notice\b|\b(?:housing\s+cost|cost|rate|price|utility|utilities)\s+increases?\b|\bincrease\s+(?:in|of|to)\s+(?:the\s+|my\s+|our\s+)?(?:rent|housing\s+cost|monthly)\b|\butilit\w+\s+(?:would\s+|will\s+)?go(?:es)?\s+up\b", prio=10,
  desc="rent increase / raised the rent / rent went up / rent keeps increasing / increase notice")
R('RENT-02', P, 'RENT_INCREASE_FEES', 'STRONG', r"\b(?:late|junk|move[- ]in|cleaning|admin\w*|pet|application|utility|notice|processing|renewal|lease\s+break\w*|reletting|additional|extra|hidden|illegal|excessive|entrance|bounce[d]?|nsf|trash|valet|amenity|service|convenience|early\s+termination|key|fob)\s+(?:check\s+)?(?:fees?|charges?)\b|\bfees?\s+(?:and|or)\s+(?:charges|deposits?)\b|\bcharg(?:ed|ing|es)\s+(?:me|us|him|her|them|the\s+tenant|tenants?|tenant)\s+(?:for|with|an?\s|extra|additional|\$)|\bcharged\s+(?:\w+\s+){0,4}?(?:additional|extra)\b|\$\s?\d[\d,.]*\s+(?:\w+\s+){0,2}fees?\b|\bgave\s+(?:me|us)\s+(?:a|an)\s+fee\b|\bdouble[- ]charged|charged\s+twice|overcharg\w*|billing\s+error|incorrect\s+charge", prio=12,
  desc="extra fees and charges: 'late fee', 'junk fees', 'charged me $75', 'double charged'")
R('RENT-03', P, 'RENT_PAYMENT_DISPUTE', 'STRONG', r"\b(?:behind|late|past\s+due|arrears|owed|overdue)\s+(?:on\s+|in\s+|with\s+)?(?:the\s+|my\s+|our\s+)?rent\b|\brent\s+(?:is\s+)?(?:due|late|owed|overdue|payment|assistance|relief|arrears|abate\w*|withh\w+|escrow\w*)\b|\b(?:withh\w+|abat\w+|escrow\w*)\s+(?:the\s+|my\s+|our\s+)?rent\b|\bback\s+rent\b|\brent\s+(?:amount|charge[sd]?)\b|\b(?:wrong|incorrect|different|disputed?)\s+(?:rent\s+)?(?:amount|amt)\b|\bwrong\s+(?:amt|amount)\s+of\s+rent\b", prio=12,
  desc="behind on rent, back rent, withholding / abating rent, wrong rent amount")
R('RENT-04', P, 'RENT_INCREASE_FEES', 'WEAK', r"\bfees?\b", prio=62, note='fee mentioned with no type stated', desc="'fee' / 'fees' with no type named (could be a lawful or unlawful charge)")
R('UBILL-01', P, 'UTILITY_BILLING', 'STRONG', r"\b(?:rubs|ratio\s+utility|utility\s+(?:billing|charges?|increase|fees?)|third[- ]?party\s+billing|3rd\s+party\s+billing|submeter\w*|sub-meter\w*|conservice|(?:water|sewer|garbage|trash)\s+(?:bill|billing|charges?)|utility\s+bills?)\b", prio=12, desc="utility billing / RUBS / third-party billing / water-sewer-garbage bill")
R('DEP-01', P, 'DEPOSIT_RETURN', 'STRONG', r"\b(?:security\s+|damage\s+|pet\s+|cleaning\s+|move[- ]in\s+)?deposits?\b", prio=12, desc="security deposit / deposit refund / deposit withheld")
R('LOCK-01', P, 'LOCKOUT_SELF_HELP', 'STRONG', r"\block(?:ed|ing|s)?[- ]?(?:me|us|him|her|them|tenants?)?[- ]?out\b|\block[- ]?outs?\b|\bchang(?:e|ed|ing)\s+(?:the\s+|my\s+|our\s+)?locks?\b|\blocks?\s+(?:were\s+|was\s+|have\s+been\s+)?changed\b|\bre-?key\w*\b|\bbarred\s+(?:me|us)\b|\b(?:belongings|possessions)\s+(?:were\s+)?(?:removed|thrown|dumped|put\s+out)\b|\bput\s+(?:my|our)\s+(?:stuff|things|belongings)\s+(?:out|on\s+the\s+(?:curb|street))\b", prio=14,
  pre_reject=r"(?:refus\w+|won't|will\s+not|failed|fail\w*|unwilling|asked|ask\w*|request\w*|need\w*|want\w*|not)\s+(?:to\s+)?$", desc="locked out, changed the locks, belongings put out (self-help eviction)")
R('RET-01', P, 'RETALIATION_HARASSMENT', 'STRONG', r"\b(?:" + RETAL + r")\b|\b" + HARASS + r"\b|\bintimidat\w*\b|\bthreaten\w*\s+(?:to\s+)?(?:evict\w*|kick|raise|call|sue|report|shut|turn|change|terminate|file|withhold|not\s+renew|harm|hurt|kill)\b|\bbull(?:y|ied|ying)\b|\b(?:" + LANDLORD + r"|owner|manager|management|mgmt|he|she|they)\s+(?:is\s+|are\s+|has\s+been\s+|keeps?\s+)?threaten\w*|\bthreatening\s+(?:tenant|me|us|him|her|them)\b|\bthreats?\s+(?:to|against|from)\b", prio=10,
  desc="retaliation, harassment, intimidation, threats by the landlord")
R('RET-02', P, 'DISCRIMINATION', 'STRONG', r"\bdiscriminat\w*\b|\bfair\s+housing\b|\bracis\w*\b|\bhomophob\w*\b", prio=10, desc="discrimination / fair housing")
R('ENTRY-01', P, 'ENTRY_PRIVACY', 'COMPOUND', r"\b(?:enter(?:ed|ing|s)?|came\s+in(?:to)?|walk(?:ed|ing)?\s+in(?:to)?|let\s+(?:himself|herself|themselves)\s+in|barg(?:ed|ing)\s+in|show(?:ed|ing)\s+up|access(?:ed)?\s+(?:my|our|the|her|his|their)\s+(?:unit|apartment|home|room|space))\b",
  cue=r"\b(?:without|no\s+(?:proper\s+|written\s+|advance\s+|prior\s+)?(?:notice|warning|permission|consent)|w/o|unannounced|improper|illegal(?:ly)?|unlawful(?:ly)?|unauthorized|proper\s+notice|permission|consent|warning|knocking|my\s+knowledge|master\s+key|using\s+a\s+key|not\s+(?:giv\w+|provid\w+|notif\w+)\s+(?:proper\s+)?notice)\b", win=60, prio=20,
  reject=r"\b(?:entry\s+(?:door|way|doors)|front\s+entry|building\s+entry|entry\s+code)\b", desc="landlord / staff entering the unit without notice or permission")
R('ENTRY-02', P, 'ENTRY_PRIVACY', 'STRONG', r"\bright\s+to\s+enter\b|\bmaster\s+key\b|\bright\s+to\s+privacy\b|\binvasion\s+of\s+privacy\b|\bviolat\w+\s+(?:my\s+|our\s+)?privacy\b|\b" + LANDLORD + r"\s+entry\b|\bunlawful\s+entry\b|\billegal\s+entry\b|\bentry\s+without\b|\bnotice\s+(?:to|of|for)\s+(?:enter|entry|inspect\w*)\b|\billegal\s+inspection\b|\binspection\s+of\s+(?:all\s+)?units\b|\b(?:24|48)\s*(?:hrs?|hours?)\s+notice\b|\bspy(?:ing|ed)?\b|\bsurveillance\b", prio=12,
  desc="landlord entry, notice to enter, master key, right to privacy")
R('ENTRY-03', P, 'ENTRY_PRIVACY', 'WEAK', r"\bprivacy\b", prio=60, note='privacy mentioned without landlord-entry context', desc="'privacy' alone (could be data privacy or landlord entry)")
R('RELO-01', P, 'RELOCATION_DISPLACEMENT', 'STRONG', r"\b(?:tenant\s+)?relocation(?:\s+(?:assistance|payment|license|benefits|funds?|money))?\b|\bdisplac(?:e|ed|ing|ement)\b|\bdispossess\w*\b|\brenovict\w*\b|\bbuy[- ]?out\b|\bcash\s+for\s+keys\b", prio=10, desc="relocation assistance, displaced, displacement, buy-out")
R('RELO-02', P, 'RELOCATION_DISPLACEMENT', 'COMPOUND', r"\b(?:demolition|demolish(?:ed|ing)?|demo|tear(?:ing)?\s+down|redevelop\w*|gut(?:ted|ting)?|rehab|remodel(?:ing|ed)?|renovat(?:e|ed|ing|ion|ions))\b", cue=r"\b(?:tenants?|move\s+out|vacate|evict\w*|notice\s+to|displac\w*|relocat\w*|leave|forced|sold|selling|new\s+owner|terminat\w*|not\s+renew\w*|lease\s+(?:ends?|terminat\w*)|being\s+asked\s+to\s+go)\b", win=70, prio=25,
  desc="demolition / remodel / renovation + tenants, notice, move out")
R('LEASE-01', P, 'LEASE_TERMS', 'STRONG', r"\b(?:lease|rental|tenancy|rental\s+agreement)\s+(?:renewal|renew\w*|expir\w*|terms?|ends?|ending|ended|violation|clause|agreement|break\w*|extension|offer)\b|\b(?:break(?:ing)?|renew(?:ing|al)?|sign(?:ing|ed)?|sublet|sublease|new|fixed[- ]term)\s+(?:a\s+|the\s+|my\s+|our\s+)?(?:lease|tenancy|agreement)\b|\bmonth[- ]to[- ]month\b|\bsubl(?:et|ease)\w*|\broommates?\b|\bco[- ]?tenant\w*|\bsubtenant\b|\bearly\s+termination\b|\brenewal\s+offer\b|\b(?:end|ending|get\s+out\s+of|out\s+of|terminate|cancel)\s+(?:the\s+|my\s+|our\s+|a\s+)?lease\b", prio=12,
  desc="lease renewal / break the lease / month-to-month / sublease / roommate")
R('NOTICE-01', P, 'NOTICE_UNSPECIFIED', 'STRONG', r"\b" + NDAY + r"s?\s*(?:written\s+)?notices?\b|\bnotice\s+(?:from|by)\s+(?:the\s+)?(?:" + LANDLORD + r"|owner|management|property)\b|\b(?:invalid|illegal|improper|defective|non-?compliant|bogus|fake)\s+(?:\w+\s+)?notices?\b|\bnotices?\s+(?:that\s+)?(?:is|are|was|were)?\s*(?:invalid|illegal|improper|defective|not\s+valid|not\s+legal|do(?:es)?\s+not\s+comply|don't\s+comply|fail\w*\s+to\s+comply)\b", prio=30,
  desc="'14-day notice' (type not stated) or a notice described as invalid / illegal")
R('REG-01', P, 'REGISTRATION_PAPERWORK', 'STRONG', r"\brental\s+(?:registration|license|inspection|housing\s+registration)\b|\bnot\s+registered\b|\bunregistered\b|\bcertificate\s+of\s+(?:compliance|registration)\b|\bregistration\b", prio=20, desc="rental registration / unregistered rental / certificate of compliance")

# ======================================================================= OTHER SDCI / NOT HOUSING
O = 'OTHER'
R('NOISE-01', O, 'NOISE_NUISANCE', 'STRONG', r"\b(?:noise|noisy|loud|music|parties|(?:loud|noisy|late[- ]night|all[- ]night)\s+party|barking|yelling|screaming|shouting|stomping|jackhammer\w*|leaf\s+blower)\b", prio=30, desc="noise, loud music, parties, barking, leaf blowers")
R('CONSTR-01', O, 'CONSTRUCTION_PERMIT', 'STRONG', r"\b(?:unpermitted|without\s+(?:a\s+)?permits?|no\s+permits?|illegal\s+(?:construction|work|remodel\w*|addition|conversion)|work\s+without|construction\s+(?:without|work|noise|dust|debris|crew|workers|concerns?|site|activity|project|hours)|contractors?)\b", prio=30, desc="unpermitted work, construction noise / dust / crews")
R('PUB-01', O, 'PUBLIC_SPACE', 'STRONG', r"\b(?:weeds?|vegetation|overgrown|bushes|trees?|branches|abandoned\s+(?:car|vehicle)|encampment|tents?|homeless|graffiti)\b", prio=40, desc="weeds, overgrown vegetation, trees, encampments, graffiti (public-space / non-housing)")
R('PUB-02', O, 'PUBLIC_SPACE', 'COMPOUND', r"\b(?:sidewalks?|parking|parked|vehicles?|alley|rv|trailer)\b", cue=r"\b(?:blocking|blocked|obstruct\w*|illegal\w*|violation|overgrown|vegetation|abandoned|too\s+many)\b", win=40, prio=40, desc="sidewalk / parking / alley + blocking, illegal, abandoned")
R('NEIGH-01', O, 'NEIGHBOR_BEHAVIOR', 'STRONG', r"\b(?:drugs?|drug\s+(?:use|users?|activity|deal\w*|house|den)|deal(?:s|ing)\s+drugs?|dealers?|crack\s*(?:hou[sz][ez]?|heads?|den)|crackhead\w*|junkies?|druggies?|tweak\w*|marijuana|needles|syringes|gunshots?|gun\s*fire|firearms?|shots\s+fired|shooting(?!\s+up)|stabbing|fight\w*|violence|assault\w*)\b", prio=40, desc="drug use / dealing, crack house, violence, gunshots (neighbor behavior)")

# ======================================================================= FLAGS (not issues; reported separately)
F = 'FLAG'
R('INQ-01', F, 'INQUIRY_RIGHTS', 'STRONG', r"\b(?:what\s+(?:are|is)\s*(?:my|our|the|his|her|their|tenant'?s?|" + LANDLORD + r"'?s?)\s*(?:legal\s+)?rights?|tenants?'?s?\s*rights|" + LANDLORD + r"'?s?\s*rights|know\s+(?:their|his|her|my|our)?\s*rights|rights\s*(?:and\s+responsibilit\w+|guidance|inquiry|questions?|information|info|regarding|as\s+a\s+(?:tenant|landlord))|my\s+rights|is\s+(?:this|that|it)\s+legal|(?:legal|tenant|housing)\s+(?:advice|resources?|assistance|help|aid|information|guidance)|(?:has|have|had)\s+questions?|questions?\s+(?:about|regarding|on|for)|wants?\s+to\s+know|would\s+like\s+to\s+(?:know|find\s+out)|how\s+(?:to|do\s+i|can\s+i|do\s+they)|inquir\w+|clarif\w+|guidance)\b", prio=60,
  desc="information request: 'what are my rights', 'wants to know', 'questions about'")
R('ROLE-01', F, 'ROLE_LANDLORD', 'STRONG', r"\b(?:i\s+am\s+(?:a\s+)?(?:" + LANDLORD + r"|owner|property\s+manager)|(?:" + LANDLORD + r"|owner|property\s+manager)(?:/owner)?\s+(?:wants?\s+to\s+(?:know|find\s+out|learn)|has\s+(?:a\s+|some\s+)?(?:code\s+)?questions?|is\s+asking|needs\s+(?:help|guidance|info\w*)|would\s+like\s+to\s+know|inquiry|question)|owner\s+rights|my\s+tenants?|our\s+tenants?|tenant\s+(?:is|was)\s+(?:creating|causing|destroy\w*|damag\w*)|tenant\s+will\s+not\s+comply|has\s+destroyed)\b", prio=60,
  desc="the caller is the owner / landlord asking, not the tenant")
R('ROLE-02', F, 'ROLE_LANDLORD', 'STRONG', r"(?<![/-])\b" + LANDLORD + r"\s+rights\b", prio=60, pre_reject=r"(?:tenant|renter)[/-]\s*$", desc="'landlord rights' (not 'tenant/landlord rights')")
R('MOD-01', F, 'MOD_NONRESPONSE', 'STRONG', r"\b(?:" + LANDLORD + r"|owner|management|manager|mgmt|property)\s+(?:is\s+|are\s+)?aware\b|\bno\s+response\b|\b(?:refus\w+|ignor\w+)\s+(?:to\s+)?(?:fix|repair|respond|address|help|do\s+anything)\b|\b(?:won't|will\s+not|hasn't|has\s+not|never)\s+(?:fix|repair|respond|answer|address)\w*\b|\bnothing\s+has\s+been\s+done\b|\bunresponsive\b|\bstill\s+not\s+(?:fixed|repaired)\b|\b(?:has\s+|have\s+|been\s+)?not\s+(?:been\s+)?(?:repaired|fixed|addressed|resolved)\b|\b(?:notified|told|informed|called|emailed|texted|contacted)\s+(?:the\s+)?(?:" + LANDLORD + r"|manager|management|owner|property\s+manager)\b|\bignor\w+\s+(?:our|my|the)\b", prio=60, desc="landlord aware / told the landlord / no response / refuses to fix (modifier)")
R('MOD-02', F, 'MOD_HEALTH', 'STRONG', r"\b(?:making\s+(?:me|us|her|him|them|the\s+tenant)\s+sick|asthma\w*|allerg\w+|respiratory|breathing|hospital\w*|sick|illness|headaches?)\b", prio=60, desc="health impact named (modifier)")
R('MOD-03', F, 'MOD_VULNERABLE', 'STRONG', r"\b(?:disabled|elderly|senior|seniors|children|child|kids|baby|infant|pregnant|handicapped|medically\s+fragile|wheelchair)\b", prio=60, desc="vulnerable household member named (modifier)")
R('INFORMAL-01', F, 'INFORMAL_SLANG', 'STRONG', r"\b(?:slum\s*lords?|slum|shit\s*hole|hell\s*hole|rat\s*hole|dump|ghetto|crap|sketchy|shady|bogus|scam|rip[- ]?off|screwed|busted|jacked|messed\s+up|trashed|nasty|gross|disgusting|y'?all|ain't|gonna|wanna|gotta|lookin|smellin|crackin|doin|nothin|somethin|cuz|dunno|pissed|freaking|wtf|omg)\b", prio=60, desc="slang / colloquial wording (vocabulary tracking only)")
R('INSULT-01', F, 'PROFANITY_OR_INSULT', 'STRONG', r"\b(?:fuck\w*|shit\w*|bitch\w*|asshole|piece\s+of\s+shit|damn|libtard\w*|idiot\w*|parasite|psycho\w*|pendejo|moron\w*|dumb\s*ass)\b", prio=60, desc="profanity / personal insult (vocabulary tracking only)")

# ======================================================================= ADDITIONS FROM RESIDUAL REVIEW
# Each rule below was added because the first pass missed real records that say exactly this (see rules_with_examples).
R('RENT-05', P, 'RENT_INCREASE_FEES', 'STRONG', r"\b(?:a)?rent\s*increase[sd]?\b|\bdouble\s*-?\s*charged\b|\bcharges?\s+dispute\b|\bdispute\w*\s+(?:of\s+)?(?:the\s+)?charges?\b|\b(?:screening|holding|application)\s+fees?\b", prio=12,
  desc="glued 'arent increase' (a rent increase), 'doublecharged', 'charges dispute', screening / holding fee")
R('RENT-06', P, 'RENT_PAYMENT_DISPUTE', 'STRONG', r"\brefus\w+\s+(?:to\s+)?(?:take|accept)\s+(?:my\s+|the\s+|our\s+)?(?:rent|rental|payment|pymt)\b", prio=12, desc="landlord refusing to accept the rent payment")
R('DEP-02', P, 'DEPOSIT_RETURN', 'STRONG', r"\bnon-?refundable\b|\bholding\s+deposit\b", prio=14, desc="non-refundable fee / holding deposit")
R('LEASE-02', P, 'LEASE_TERMS', 'STRONG', r"\blease\s+(?:is\s+)?(?:about\s+to\s+)?(?:expire[sd]?|expiring|up|ends?|ended|ending)\b|\b(?:no|without|never\s+(?:given|received|signed|provided))\s+(?:a\s+)?(?:written\s+|signed\s+)?lease\b|\bhasn't\s+given\s+(?:the\s+)?tenant\s+(?:a\s+)?lease\b", prio=12, desc="lease about to expire, no written lease given")
R('EVICT-07', P, 'EVICTION_TERMINATION', 'STRONG', r"\b(?:he|she|they)\s+(?:will|is\s+going\s+to|wants?\s+to|plans?\s+to)\s+move\s+in\b|\bNTQ\b|\bnotice\s+to\s+quit\b", prio=10, desc="owner says they will move in; NTQ (notice to quit) shorthand")
R('ENTRY-04', P, 'ENTRY_PRIVACY', 'STRONG', r"\bnotices?\s+(?:to|of|for)\s+(?:an?\s+)?(?:\w+\s+)?(?:enter|entry|inspect\w*)\b|\bnotices?\s+of\s+intent\s+to\s+enter\b|\bprivacy\s+(?:has\s+been\s+|was\s+|is\s+)?(?:invad\w*|violat\w*)\b", prio=12, desc="notice of intent to enter / inspection notice; privacy invaded")
R('RET-03', P, 'RETALIATION_HARASSMENT', 'STRONG', r"(?<=[a-z])(?:retaliat\w*|harass\w*|intimidat\w*)\b", prio=10, desc="retaliation / harassment glued to the previous word ('beingretaliated')")
R('INQ-02', F, 'INQUIRY_RIGHTS', 'STRONG', r"\b(?:more\s+)?information\s+(?:regarding|about|on|re:?)\b|\bmore\s+info\b|\bpolicy\s+questions?\b|\blandlord\s+q\b|\bcan\s+(?:a\s+|the\s+|my\s+)?(?:landlord|owner|manager|management)\b|\bcan\s+(?:i|we)\s+(?:legally|be|get|break|terminate|refuse|withhold)\b|\bcan\s+they\s+(?:legally|really)\b|\bis\s+it\s+legal\b|\bdo\s+(?:i|we)\s+have\s+to\b|\bam\s+i\s+required\b|\bdo\s+i\s*have\s+any\s+rights\b|\bwhat\s+can\s+(?:i|we)\s+do\b", prio=60, desc="information request: 'more information regarding', 'can a landlord', 'do I have to'")
R('HEAT-05', H, 'HEAT', 'COMPOUND', r"\b(?:in\s+the\s+)?(?:low|mid|high)\s+[3-6]0s\b|\b[3-6]\d\s*(?:degrees|\xb0)", cue=r"\b(?:heat\w*|cold|freez\w*|temp\w*|apartment|unit|building|hall\w*|lobby|inside|indoors?|rooms?|house|home|bedroom|thermostat|boiler|furnace|radiators?|chill\w*|below|dropp\w*|cool\w*|warm\w*)\b", win=70, prio=18, reject=r"\boutside\b|\bweather\b|\bforecast\b|\boutdoors?\b",
  desc="inference: indoor temperature in the 30s-60s with heat / cold / unit words in the same clause ('it is 56 degrees in our building')")
R('HW-04', H, 'HOT_WATER', 'STRONG', r"\b(?:scald\w*|scorch\w*)\b|\b(?:too|extremely|dangerously|very)\s+hot\s+water\b|\bhot\s+water\s+(?:is\s+)?(?:too|extremely|dangerously|very)\s+hot\b|\bwater\s+(?:has\s+been|is|was|been)\s+cold\b|\bfrigid\s+cold\b", prio=18, desc="hot water scalding or turning cold: 'water has been cold for five days', 'scalding'")
R('WATER-04', H, 'WATER_SERVICE', 'STRONG', r"\bwater\s+(?:will\s+be\s+|going\s+to\s+be\s+)(?:shut[\s-]*(?:off|down)|turned\s+off|cut\s+off|disconnected)\b", prio=10, desc="notice that the water WILL be shut off", group='UTIL')
R('DOOR-06', H, 'DOORS_WINDOWS_SECURITY', 'COMPOUND', r"\b(?:locks?|deadbolts?|latch\w*|door\s*frames?|window\s*frames?|handles?)\b", cue=r"\b(?:malfunction\w*|jiggle|jammed|stuck|broken|busted|loose|damaged|key\s+only)\b|" + CUE_NOTWORK + "|" + CUE_UNFIXED, win=50, prio=18, desc="lock / latch / door frame / handle + malfunction, jammed, broken, 'not all working'")
R('DOOR-07', H, 'DOORS_WINDOWS_SECURITY', 'STRONG', r"\bno\s+(?:thumb\s*(?:latch|turn)|dead\s*bolt|bars|window\s+guards?)\b|\b(?:fell|fall|falling)\s+out\s+of\s+(?:the\s+|a\s+|my\s+)?(?:\w+\s+)?window\b|\bwindows?\s+(?:have\s+)?no\s+(?:bars|guards?|stops?)\b", prio=10, desc="no thumb latch, no window guards, child almost fell out of window")
R('STRUCT-05', H, 'STRUCTURAL', 'STRONG', r"\bstair\s+treads?\b|\btreads?\s+(?:on|of)\s+(?:the\s+)?(?:stairs?|staircase|steps?)\b|\brisers?\b|\b(?:head\s*room|guard\s*rail|guardrail|ceiling\s+height|windowless|no\s+egress)\b", prio=20, desc="building-code dimensions: stair tread / riser, headroom, guardrail, ceiling height, no egress")
R('HABU-02', H, 'HAB_UNSPECIFIED', 'STRONG', r"\bnot\s+(?:to|up\s+to)\s+code\b|\bnot\s+code[- ]?compliant\b|\brepairs?\s+(?:are\s+|is\s+|being\s+)*(?:ignored|not\s+(?:being\s+)?(?:done|made|addressed|completed))\b|\b(?:urgent|needed|necessary|outstanding|overdue)\s+repairs?\b|\bmaintenance\s+(?:is\s+)?(?:ignored|not\s+(?:done|being\s+done))\b|\bfailed\s+to\s+(?:fix|repair|maintain)\b|\brefus\w+\s+(?:to\s+make\s+)?repairs?\b", prio=50, desc="general maintenance neglect: 'repairs being ignored', 'not up to code', 'failed to maintain'")
R('HAZ-03', H, 'HAZMAT_AIR', 'PRESENCE', r"\bdiesel\b|\bexhaust\b(?!\s+(?:fans?|vent|hood))|\bsmoke\s+(?:keeps?\s+)?(?:entering|coming|going|drifting|seeping)\s+(?:in|into|through)\b|\bsmoke\s+through\s+(?:the\s+)?vents?\b|\bcigarette\s+smoke\b|\bsmok(?:e|ing)\s+in\s+(?:the\s+)?(?:building|hallway|unit)\b", prio=18, desc="diesel / exhaust fumes, cigarette smoke drifting through vents")
R('PEST-04', H, 'PESTS', 'PRESENCE', r"\b(?:crickets?|beetles?|centipedes?|millipedes?|weevils?|carpenter\s+ants?|yellow\s*jackets?)\b", prio=12, desc="crickets, beetles, centipedes, yellow jackets (less common pests)")
R('NOISE-02', O, 'NOISE_NUISANCE', 'STRONG', r"\b(?:band\s+playin\w*|drums?|guitars?|amplif\w+|subwoofers?|crowing|rooster)\b", prio=30, reject=r"rooster\s+apartments?", desc="band practice, drums, amplifiers, rooster crowing")
R('CONSTR-02', O, 'CONSTRUCTION_PERMIT', 'STRONG', r"\bunder\s+construction\b|\bconstruction\b|\bcertificate\s+of\s+occupancy\b|\bdevelop(?:er|ment)\b|\bjack\s*hammer\w*\b|\bconcrete\s+(?:pump|truck|slurry)\b", prio=34, desc="construction activity, certificate of occupancy, developer, jackhammer")
R('PUB-03', O, 'PUBLIC_SPACE', 'COMPOUND', r"\b(?:right[- ]of[- ]way|row\b|streets?|roads?|pavement|gutters?|storm\s+drain|drainage|alley)\b", cue=r"\b(?:construction|developer|cut|plates?|damaged?|cracked|blocked|blocking|dump\w*|spill\w*|improper|illegal|mud|debris|trailer|stored|storing)\b", win=60, prio=42, desc="street / right-of-way / drainage + construction, blocked, dumping")
R('PUB-04', O, 'PUBLIC_SPACE', 'STRONG', r"\b(?:bush|shrubs?|hedges?|stumps?)\b", prio=44, desc="bush / shrub / hedge (vegetation)")
R('ZONE-01', O, 'ZONING_USE', 'STRONG', r"\bnot\s+zoned\b|\bzoning\b|\bunapproved\b|\bhome\s+business\b|\bshort[- ]term\s+rental\b|\bairbnb\b|\billegal\s+(?:unit|use|conversion|sro)\b|\b(?:adu|dadu)\b|\brooming\s+house\b|\bsro\b|\bsingle\s+room\s+occupancy\b", prio=36, desc="zoning / illegal unit / short-term rental / SRO (land-use rather than housing condition)")
R('APPL-02', H, 'APPLIANCES_FIXTURES', 'COMPOUND', r"\b(?:dishwasher|stove|oven|refrigerator|fridge|washer|dryer|appliances?)\b", cue=r"\b(?:delay\w*|waiting\s+for|overdue|dysfunctional)\b", win=60, prio=32, desc="appliance + delay / waiting for repair")
R('ELEV-03', H, 'ELEVATOR_ACCESS', 'COMPOUND', r"\b(?:elevators?|lifts?)\b", cue=r"\b(?:dysfunctional|inconsistent\w*|unreliable|intermittent\w*)\b", win=80, prio=16, desc="elevator dysfunctional / inconsistent")
R('INSULT-02', F, 'PROFANITY_OR_INSULT', 'STRONG', r"\b(?:scum\w*|crooks?|corrupt\w*|criminals?|crime\s+family|garbage\s+dump|stupid)\b", prio=60, desc="insult wording (vocabulary tracking only)")

# ---- second residual pass: wording found by comparing text against the city's own labels in DESCRIPTION1
R('RENT-07', P, 'RENT_INCREASE_FEES', 'STRONG', r"\b(?:now\s+)?being\s+charged\b|\bparking\s+(?:fees?|charges?)\b|\b(?:new|added|extra)\s+(?:fees?|charges?)\b|\bfees?\s+(?:added|increased)\b", prio=12, desc="'now being charged', parking fees, new / added fees")
R('EVICT-08', P, 'EVICTION_TERMINATION', 'STRONG', r"\bend(?:ing)?\s+(?:of\s+)?(?:the\s+|my\s+|our\s+)?tenancy\b|\btenancy\s+(?:ending|ended|is\s+ending)\b|\b(?:forced\s+)?mutual\s+termination\b|\b(?:pay|sign|comply|agree)\b.{0,40}\bor\s+(?:get\s+out|leave|move\s+out|vacate)\b", prio=10, desc="'end of tenancy notice', 'mutual termination', 'pay or get out'")
R('EVICT-09', P, 'EVICTION_TERMINATION', 'WEAK', r"\b(?:selling|sale\s+of|sold)\s+(?:the\s+|this\s+|our\s+)?(?:property|building|house|home|unit)\b", prio=65, note='sale of the property mentioned, no notice stated (possible no-fault termination)', desc="property being sold, no notice or deadline stated")
R('LEASE-03', P, 'LEASE_TERMS', 'STRONG', r"\blease\s+(?:that\s+)?(?:ended|expired)\b|\bterm\s+lease\b", prio=12, desc="lease that ended / term lease")
R('DEP-03', P, 'DEPOSIT_RETURN', 'WEAK', r"\brefund\w*\b", prio=62, note='refund mentioned without saying what for (deposit assumed)', desc="'refund' with no deposit named")
R('FIRE-09', H, 'FIRE_SMOKE_CO_GAS', 'STRONG', r"\bgives?\s+off\s+gas\b|\bgas\s+(?:that\s+)?filter\w*\b|\bgas\s+fumes?\b|\brecent\s+fire\b|\bdoors?\s+lock\w*\s+when\s+the\s+fire\s+alarm\b", prio=6, desc="gas seeping into a unit, recent fire, doors that lock when the fire alarm sounds")
R('HABU-03', H, 'HAB_UNSPECIFIED', 'STRONG', r"\b(?:inadequate|poor)\s+(?:building\s+)?(?:maintenance|upkeep|repairs?)\b|\black\s+of\s+(?:maintenance|upkeep)\b", prio=50, desc="inadequate / poor maintenance and upkeep")
R('UTIL-04', H, 'WATER_SERVICE', 'STRONG', r"\b(?:shut[\s-]*(?:off|down)|turned?\s+off|cut\s+off|disconnected)\s+(?:the\s+|my\s+|our\s+|all\s+)?water\b", prio=10, reject=r"\b(?:trees?|plants?|lawn|garden|valve)\b", desc="owner shut off / disconnected the water (verb first)", group='UTIL')
R('UTIL-05', H, 'ELECTRICAL', 'STRONG', r"\b(?:shut[\s-]*(?:off|down)|turned?\s+off|cut\s+off|disconnected)\s+(?:the\s+|my\s+|our\s+|all\s+)?(?:electricity|electric|power)\b", prio=10, desc="owner shut off / disconnected the electricity (verb first)", group='UTIL')
R('UTIL-06', H, 'HEAT', 'STRONG', r"\b(?:shut[\s-]*(?:off|down)|turned?\s+off|cut\s+off|disconnected)\s+(?:the\s+|my\s+|our\s+|all\s+)?(?:heat|heating)\b", prio=10, desc="owner shut off the heat (verb first)", group='UTIL')
R('ELEC-06', H, 'ELECTRICAL', 'STRONG', r"\bno\s+(?:working\s+)?(?:lights?|lighting)\b|\blights?\s+(?:are\s+|is\s+)?(?:out|off)\b", prio=12, desc="'no lights', 'lights are out'")
R('ELEV-04', H, 'ELEVATOR_ACCESS', 'COMPOUND', r"\b(?:elevators?|lifts?)\b", cue=CUE_NOTWORK + "|" + CUE_UNFIXED + "|" + CUE_OUT, win=80, prio=15, desc="elevator + 'have not been working', 'not fixed', 'is out'")
R('FIRE-10', H, 'FIRE_SMOKE_CO_GAS', 'COMPOUND', r"\b(?:smoke\s+(?:detectors?|alarms?)|alarms?|co\s+detectors?)\b", cue=r"\b(?:refus\w+\s+to\s+install|not\s+install\w*|never\s+install\w*|haven't\s+installed|no\s+alarms?\s+any\s*where)\b", win=60, prio=9, desc="landlord refuses to install smoke alarms / no alarms anywhere")
R('NEIGH-02', O, 'NEIGHBOR_BEHAVIOR', 'STRONG', r"\b(?:fentanyl|heroin|opioids?|smoke\s+from\s+(?:drugs?|meth|crack))\b", prio=40, desc="fentanyl / heroin smoke from drug use (neighbor behavior)")

# ---- third residual pass (old-script cases the first rules missed)
R('RET-04', P, 'RETALIATION_HARASSMENT', 'WEAK', r"\b(?:after|because|in\s+response\s+to)\s+(?:i|we|he|she|they|the\s+tenants?|tenants?)\s+(?:had\s+|have\s+)?(?:complain\w*|report\w*|ask\w*\s+(?:for\s+)?(?:the\s+)?repairs?|request\w*\s+(?:the\s+)?repairs?|fil\w+\s+(?:a\s+)?complaints?|call(?:ed)?\s+(?:the\s+city|sdci|code\s+enforcement|an?\s+inspector)|contact\w*\s+(?:the\s+city|sdci))\b", prio=64,
  note='something happened after the tenant complained or reported (retaliation implied, not stated)', desc="'after I complained', 'because I reported' (retaliation implied but not stated; 'since' is left out because it is usually a time word)")
R('EVICT-10', P, 'EVICTION_TERMINATION', 'COMPOUND', r"\b(?:(?:[2-9]\d|1\d\d)\s*-?\s*days?|(?:twenty|thirty|sixty|ninety)\s*-?\s*days?)\s*(?:written\s+)?notices?\b",
  cue=r"\b(?:demoli\w*|redevelop\w*|substantial\w*|rehab\w*|renovat\w*|remodel\w*|sell\w*|sale|sold|change\s+of\s+use|owner\s+move|move\s+in|vacate|terminat\w*|end\s+(?:of\s+)?(?:the\s+)?(?:lease|tenancy)|leav\w+|move\s+out)\b", win=70, prio=9,
  desc="'90 day notice' + demolition / redevelopment / sale / vacate (a termination notice with its reason stated; 20+ days so a 3-day entry notice is not counted)")

# ---- fourth pass: RRIO as tenant vocabulary, electrical panels, and shared-phrase rules
R('REG-02', P, 'REGISTRATION_PAPERWORK', 'COMPOUND', r"\bRRIO\b",
  cue=r"\b(?:certificates?|registered|register\w*|registration|expir\w*|exempt\w*|complian\w*|non-?compliant|checklist|violat\w*|licen[cs]e\w*|inspect\w*|program|requirements?|ordinance|required|comply|enroll\w*|not\s+have|doesn't\s+have|does\s+not\s+have|no\s+rrio|without|lapsed|valid\w*)\b", win=60, prio=16, weak_alone=True,
  desc="'RRIO' written in a sentence (not as a staff label) + certificate / register / expired / inspection / compliant; bare 'RRIO' = borderline")
R('ELEC-07', H, 'ELECTRICAL', 'COMPOUND', r"\b(?:breaker\s*box(?:es)?|electrical\s+panels?|fuse\s*box(?:es)?|main\s+panel|breaker\s+panel)\b",
  cue=r"\b(?:no\s+access|access|located|inside|bedroom|closet|uncovered|exposed|blocked|locked|tripp\w*|trips?|overload\w*|buzz\w*|burn\w*|sparks?|sparking|shock\w*|melted|rusted|corroded|flooded|loose)\b", cue2=CUE_PROBLEM, win=70, prio=18, weak_alone=True,
  desc="breaker box / electrical panel + no access, located in a bedroom, exposed, tripping, sparking; panel mentioned alone = borderline")

# retaliation and eviction wording may share one phrase ("threatened eviction", "retaliatory eviction"): both are counted
for _r in RULES:
    if _r.cat in ('RETALIATION_HARASSMENT', 'EVICTION_TERMINATION'): _r.group = 'EVR'

# ---- context flag kept for parity with the old script (it flagged SHA = Seattle Housing Authority)
R('CTX-01', 'FLAG', 'CONTEXT_SHA', 'STRONG', r"\b(?:seattle\s+housing\s+authority|(?-i:SHA))\b", prio=60, desc="Seattle Housing Authority (SHA) named - context flag, not an issue")


# ====================================================================================================
# MATCHER
# ====================================================================================================
import re

CLAUSE_SEP = re.compile(r"\s+(?:but|however|although|though|while|whereas|yet|except)\s+|\s*;\s*", re.I)
PRONOUN_AFTER = re.compile(r"\s*(?:they|it|these|those|this|that)\b", re.I)   # "2 elevators, but they have not been working" - same subject continues
RULE_ORDER = [r for _, r in sorted(enumerate(RULES), key=lambda x: (x[1].prio, x[0]))]
OBJ_ANY = re.compile('|'.join('(?:%s)' % r.pat for r in RULES if r.kind == 'COMPOUND'), re.I)
_SKIPWORDS = re.compile(r"(?:\s+(?!(?:and|or|but|also|then|with|plus|from|to|in|on|at|of|the|a|an|by|for|into|onto|through|out|up|down|off|is|are|was|were|has|have|had)\b)[A-Za-z']+){0,1}\s+", re.I)
NEG_EXCEPT_AFTER = re.compile(r"\s+(?:check|checks|test|tests|testing|inspection|abatement|remediation|treatment|removal|clean\w*|assessment|report)\b", re.I)

def cue_taken(claimed, rule, cs, ce):
    for (ca, cb, ccat, crule, cgrp) in claimed:
        if cs < cb and ce > ca and ccat != rule.cat and not (rule.group and rule.group == cgrp): return True
    return False

def binds_to_next(tm, cs, ce):
    """a 'broken'/'busted' type adjective directly in front of another object belongs to that object"""
    word = tm[cs:ce].lower().strip()
    if word not in PRENOM_ADJ: return False
    m = _SKIPWORDS.match(tm, ce)
    if not m: return False
    return bool(OBJ_ANY.match(tm, m.end()))

def prep(raw, gm=None):
    t0 = clean(raw)
    t1 = apply_glue(t0, gm or {})
    ch, end = channel_of(t1)
    tm = (' ' * end + t1[end:]) if end else t1
    tm, labels = mask_labels(tm)
    return t0, t1, tm, ch, labels

def analyze(raw, gm=None, rules=None):
    t0, t1, tm, ch, labels = prep(raw, gm)
    author = authorship(raw, labels, tm)
    lang = language_of(raw)
    segs = segments(tm)
    out = []; claimed = []
    workflow = (author == 'STAFF_WORKFLOW_NOTE')
    for rule in (rules or RULE_ORDER):
        for (s, e) in segs:
            seg = tm[s:e]
            if not seg.strip(): continue
            cand = []   # dicts: a,b,dec,why,obj,cue
            if rule.kind == 'COMPOUND':
                for m in rule.rx.finditer(seg):
                    os_, oe = s + m.start(), s + m.end()
                    if rule.pre_reject and rule.pre_reject.search(tm[max(0, os_ - 16):os_]):
                        continue
                    if rule.reject and rule.reject.search(tm, max(s, os_ - 25), min(e, oe + 25)):
                        cand.append(dict(a=os_, b=oe, dec='REJECT_CONTEXT', why='reject-context pattern near object', obj=(os_, oe), cue=None)); continue
                    ws = max(s, os_ - rule.win); we = min(e, oe + rule.win)
                    for sm in CLAUSE_SEP.finditer(tm, ws, os_):
                        ws = max(ws, sm.end())
                    sm = CLAUSE_SEP.search(tm, oe, we)
                    if sm and not PRONOUN_AFTER.match(tm, sm.end()): we = min(we, sm.start())
                    best = None
                    for cm in rule.cue.finditer(tm, ws, we):
                        cs, ce = cm.start(), cm.end()
                        if cs < oe and ce > os_: continue
                        if cs >= oe and binds_to_next(tm, cs, ce): continue
                        if cue_taken(claimed, rule, cs, ce): continue
                        dist = min(abs(cs - oe), abs(os_ - ce))
                        if best is None or dist < best[0]: best = (dist, cs, ce)
                    if best is None and rule.cue2 is not None:
                        ws2 = max(ws, os_ - rule.nwin); we2 = min(we, oe + rule.nwin)
                        for cm in rule.cue2.finditer(tm, ws2, we2):
                            cs, ce = cm.start(), cm.end()
                            if cs < oe and ce > os_: continue
                            if cue_taken(claimed, rule, cs, ce): continue
                            between = tm[oe:cs] if cs >= oe else tm[ce:os_]
                            if re.search(r"[,;:.()]", between): continue
                            dist = min(abs(cs - oe), abs(os_ - ce))
                            if best is None or dist < best[0]: best = (dist, cs, ce)
                    if best:
                        cand.append(dict(a=min(os_, best[1]), b=max(oe, best[2]), dec='ACCEPT', why='object + failure/problem cue in same clause', obj=(os_, oe), cue=(best[1], best[2])))
                    elif rule.weak_alone:
                        cand.append(dict(a=os_, b=oe, dec='BORDERLINE', why='object term with no failure cue in same clause', obj=(os_, oe), cue=None))
            else:
                for m in rule.rx.finditer(seg):
                    ms, me = s + m.start(), s + m.end()
                    if rule.pre_reject and rule.pre_reject.search(tm[max(0, ms - 16):ms]):
                        continue
                    if rule.reject and rule.reject.search(tm, max(s, ms - 25), min(e, me + 25)):
                        cand.append(dict(a=ms, b=me, dec='REJECT_CONTEXT', why='reject-context pattern near match', obj=(ms, me), cue=None)); continue
                    if rule.kind == 'WEAK':
                        cand.append(dict(a=ms, b=me, dec='BORDERLINE', why=rule.note or 'weak/ambiguous term', obj=(ms, me), cue=None)); continue
                    if (rule.kind == 'PRESENCE' or rule.neg) and negated(tm, ms, s) and not NEG_EXCEPT_AFTER.match(tm, me):
                        cand.append(dict(a=ms, b=me, dec='REJECT_NEGATED', why='negation immediately before the term', obj=(ms, me), cue=None)); continue
                    cand.append(dict(a=ms, b=me, dec='ACCEPT', why='phrase match', obj=(ms, me), cue=None))
            for c in cand:
                a, b, dec = c['a'], c['b'], c['dec']
                oa, ob = c['obj']
                if rule.lane != 'FLAG' and dec in ('ACCEPT', 'BORDERLINE'):
                    clash = None; dup = False
                    for (ca, cb, ccat, crule, cgrp) in claimed:
                        if oa < cb and ob > ca:
                            if ccat == rule.cat: dup = True
                            elif rule.group and rule.group == cgrp: pass
                            else: clash = (ccat, crule)
                    if dup: continue
                    if clash:
                        out.append(dict(rule=rule.id, lane=rule.lane, cat=rule.cat, kind=rule.kind, sev=rule.sev, decision='REJECT_OVERLAP',
                                        reason=f'span already claimed by {clash[0]} ({clash[1]})', start=a, end=b, phrase=tm[a:b], obj=tm[oa:ob], cue=''))
                        continue
                    if dec == 'ACCEPT':
                        claimed.append((oa, ob, rule.cat, rule.id, rule.group))      # only the object / phrase is claimed, never the cue word
                phrase = tm[a:b]
                cuetxt = ''
                if c['cue']:
                    cuetxt = tm[c['cue'][0]:c['cue'][1]]
                    gap = (c['cue'][0] - ob) if c['cue'][0] >= ob else (oa - c['cue'][1])
                    if gap > 25:
                        phrase = (tm[oa:ob] + ' … ' + cuetxt) if c['cue'][0] >= ob else (cuetxt + ' … ' + tm[oa:ob])
                out.append(dict(rule=rule.id, lane=rule.lane, cat=rule.cat, kind=rule.kind, sev=rule.sev, decision=dec, reason=c['why'], start=a, end=b, phrase=phrase, obj=tm[oa:ob], cue=cuetxt))
    return dict(text=tm, orig=t1, clean=t0, channel=ch, labels=labels, author=author, lang=lang, matches=out)


# ============================================================================ PIPELINE: load -> analyse -> aggregate

VERSION = '1.0.0'

LANE_NAME = {'HAB': 'Habitability (landlord-tenant AND SDCI housing code)', 'PAPER': 'Paperwork / landlord-tenant law (notices, rent, deposits, entry, retaliation)',
             'OTHER': 'Other SDCI / not housing (noise, construction, public space, zoning, neighbor behavior)', 'FLAG': 'Flags (not issues)'}
CAT_LABEL = {
 'HEAT': 'Heat', 'HOT_WATER': 'Hot water', 'WATER_SERVICE': 'Water service, pressure, quality', 'LEAKS_WATER_INTRUSION': 'Leaks, flooding, water intrusion',
 'PLUMBING_SEWAGE': 'Plumbing and sewage', 'MOLD_MOISTURE': 'Mold and moisture', 'PESTS': 'Pests (bed bugs, roaches, rodents)', 'ELECTRICAL': 'Electrical and power',
 'STRUCTURAL': 'Structural / building envelope', 'DOORS_WINDOWS_SECURITY': 'Doors, windows, locks, mail, security', 'FIRE_SMOKE_CO_GAS': 'Fire, smoke/CO alarms, gas, exits',
 'ELEVATOR_ACCESS': 'Elevator and accessibility', 'SANITATION_ODOR': 'Sanitation, trash, odors', 'HAZMAT_AIR': 'Hazardous materials, fumes, ventilation',
 'APPLIANCES_FIXTURES': 'Appliances and fixtures', 'HVAC_COOLING': 'Air conditioning / HVAC (cooling)', 'UTILITY_SERVICE_LOSS': 'Gas / utility service loss',
 'OVERCROWDING': 'Overcrowding / occupancy', 'HAB_UNSPECIFIED': 'General habitability (no defect named)', 'UNINHABITABLE_SEVERITY': 'Uninhabitable / unfit (severity)',
 'PAPER_UNSPECIFIED': 'Paperwork (city label only, issue not stated)', 'OTHER_UNSPECIFIED': 'Other SDCI (city label only)',
 'EVICTION_TERMINATION': 'Eviction and termination', 'NOTICE_UNSPECIFIED': 'Notice (type not stated)', 'RENT_INCREASE_FEES': 'Rent increases, fees, charges',
 'RENT_PAYMENT_DISPUTE': 'Rent payment disputes', 'UTILITY_BILLING': 'Utility billing (RUBS, third-party)', 'DEPOSIT_RETURN': 'Deposits and refunds',
 'LOCKOUT_SELF_HELP': 'Lockouts and self-help', 'RETALIATION_HARASSMENT': 'Retaliation and harassment', 'DISCRIMINATION': 'Discrimination / fair housing',
 'ENTRY_PRIVACY': 'Landlord entry and privacy', 'RELOCATION_DISPLACEMENT': 'Relocation and displacement', 'LEASE_TERMS': 'Lease terms, renewal, roommates',
 'REGISTRATION_PAPERWORK': 'Rental registration paperwork', 'NOISE_NUISANCE': 'Noise', 'CONSTRUCTION_PERMIT': 'Construction / permits', 'PUBLIC_SPACE': 'Public space (weeds, sidewalks, parking)',
 'NEIGHBOR_BEHAVIOR': 'Neighbor behavior (drugs, violence)', 'ZONING_USE': 'Zoning / illegal unit / land use',
 'INQUIRY_RIGHTS': 'Information request / rights question', 'ROLE_LANDLORD': 'Caller is the landlord / owner', 'MOD_NONRESPONSE': 'Landlord aware / not responding',
 'CONTEXT_SHA': 'Seattle Housing Authority (SHA) named', 'MOD_HEALTH': 'Health impact named', 'MOD_VULNERABLE': 'Vulnerable household member named', 'INFORMAL_SLANG': 'Slang / colloquial wording', 'PROFANITY_OR_INSULT': 'Profanity / insult',
}
UNSPEC = {'HAB_UNSPECIFIED', 'NOTICE_UNSPECIFIED', 'PAPER_UNSPECIFIED', 'OTHER_UNSPECIFIED'}
SEVERITY = {'UNINHABITABLE_SEVERITY'}
TENANT_VOICE = ('TENANT_FIRST_PERSON', 'ONLINE_FORM_TEXT')
STAFF_CLASSES = ('STAFF_PHONE_SUMMARY', 'STAFF_THIRD_PERSON', 'STAFF_CODE_LABEL', 'STAFF_WORKFLOW_NOTE', 'STAFF_LABEL_ONLY', 'STAFF_RELAY_OF_WRITTEN', 'FORM_TEMPLATE')
AUTHOR_LABEL = {
 'TENANT_FIRST_PERSON': 'Tenant wording (first person: I / my / we)', 'ONLINE_FORM_TEXT': 'Online form text ("Per online...", staff wrapper + submitted text)',
 'STAFF_PHONE_SUMMARY': 'Staff-typed phone summary ("per phone call")', 'STAFF_THIRD_PERSON': 'Staff narrative (third person: "complainant states...")',
 'STAFF_WORKFLOW_NOTE': 'Staff workflow note (TRAO / EDRA permit hold, packet, help)', 'STAFF_LABEL_ONLY': 'City label only (nothing else in the text)',
 'STAFF_CODE_LABEL': 'Staff code citation / label (SMC, RCW)', 'STAFF_RELAY_OF_WRITTEN': 'Staff relay of a letter / email', 'FORM_TEMPLATE': 'Form template (service-request boilerplate)',
 'SHORT_UNATTRIBUTED': 'Short phrase (6 words or fewer) - author not established', 'NEUTRAL_UNATTRIBUTED': 'Neutral declarative text - author not established',
 'MIXED_MARKERS': 'Mixed first-person and staff markers', 'EMPTY': 'No text',
}

def lane_of_cat(cat, rules):
    for r in rules:
        if r.cat == cat: return r.lane
    return 'FLAG'

# ---------------------------------------------------------------------------- loading
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 20), b''): h.update(ch)
    return h.hexdigest()

def load_records(path):
    data = json.load(open(path, encoding='utf-8-sig'))
    if isinstance(data, dict):
        for k in ('records', 'rows', 'data'):
            if isinstance(data.get(k), list): data = data[k]; break
    return data

def norm_district(v):
    s = '' if v is None else str(v).strip()
    return s if s in ('1', '2', '3', '4', '5', '6', '7') else 'UNKNOWN'

def truth(v): return str(v).strip().lower() in ('true', '1', 'yes', 'y')

# ---------------------------------------------------------------------------- per-record analysis (runs in worker processes)
_GM = None
def _init_worker(gm):
    global _GM
    _GM = gm

def analyze_worker(r):
    desc = r.get('DESCRIPTION') or ''
    a = analyze(desc, _GM)
    return r['RECORDNUM'], a

def run_analysis(records, gm, workers=None):
    """records: list of raw dicts (complaints only). Returns {recordnum: analysis}"""
    import multiprocessing as mp
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    out = {}
    if workers == 1:
        _init_worker(gm)
        for r in records:
            k, a = analyze_worker(r); out[k] = a
        return out
    with mp.Pool(workers, initializer=_init_worker, initargs=(gm,)) as pool:
        for k, a in pool.imap_unordered(analyze_worker, records, chunksize=250):
            out[k] = a
    return out

# ---------------------------------------------------------------------------- D1 label extraction
D1_LABEL_RX = re.compile(r"\b(?:POTA|JCEO|TRAO|EDRA|RRIO|HBMC|HZW|HZT|CSB|RARO|ROFR|INRENT|RENTAG|PAOTHR|OTHR|DEPOSIT|HOUSING|EMERGENCY|WEEDS|ZONING|UNFIT|NOISE|CONSTRUCTION|VB|HAZARDOUS WEEDS|NO VIOLATION|ADMIN CLOSURE|WITHDRAWN|DUPLICATE)\b")
def d1_labels(d1):
    return sorted(set(m.group(0) for m in D1_LABEL_RX.finditer((d1 or '').upper())))

# ---------------------------------------------------------------------------- record finalisation
def finalize_record(raw, a, rules, lane_map, decisions=None, label_infer=None):
    """Turn raw matches into the per-record result used by every table."""
    rid = raw['RECORDNUM']
    acc = defaultdict(list); bord = defaultdict(list); rej = []
    for m in a['matches']:
        d = m['decision']
        if d == 'ACCEPT': acc[m['cat']].append(m)
        elif d == 'BORDERLINE': bord[m['cat']].append(m)
        else: rej.append(m)
    if decisions:
        for (r_id, cat), dec in decisions.items():
            if r_id != rid: continue
            if dec == 'ACCEPT' and cat in bord: acc[cat].extend(bord.pop(cat))
            elif dec == 'REJECT': acc.pop(cat, None); bord.pop(cat, None)
    cats_A = sorted(c for c in acc if lane_map.get(c) in ('HAB', 'PAPER', 'OTHER'))
    flags = sorted(c for c in acc if lane_map.get(c) == 'FLAG')
    cats_B = sorted(c for c in bord if c not in acc and lane_map.get(c) in ('HAB', 'PAPER', 'OTHER'))
    d1 = (raw.get('DESCRIPTION1') or '').strip()
    labs = d1_labels(d1)
    cats_L = []
    if label_infer and not cats_A:
        for lab in labs:
            for c in label_infer.get(lab, []):
                if c not in cats_L: cats_L.append(c)
    specific = [c for c in cats_A if c not in UNSPEC and c not in SEVERITY]
    n_issues = len(specific) if specific else (1 if [c for c in cats_A if c not in SEVERITY] else 0)
    lanes = sorted({lane_map[c] for c in cats_A if c not in SEVERITY})
    lane_key = '+'.join(lanes) if lanes else ''
    if not lane_key:
        if 'INQUIRY_RIGHTS' in flags: lane_key = 'INQUIRY_ONLY'
        elif a['author'] in ('STAFF_WORKFLOW_NOTE', 'STAFF_LABEL_ONLY'): lane_key = 'STAFF_NOTE_ONLY'
        elif cats_B or cats_L: lane_key = 'UNCONFIRMED'
        else: lane_key = 'NO_ISSUE_WORDS'
    return dict(
        id=rid, year=int(str(raw.get('OPENDATE'))[:4]) if raw.get('OPENDATE') else 0, district=norm_district(raw.get('DISTRICT')),
        tdesc=raw.get('RECORDTYPEDESC') or '', review_only=truth(raw.get('LLT_REVIEW_ONLY')), group=raw.get('LLT_GROUP') or '',
        status=raw.get('STATUSCURRENT') or '', address=raw.get('ORIGINALADDRESS1') or '', opendate=str(raw.get('OPENDATE') or '')[:10],
        author=a['author'], channel=a['channel'] or '', lang=a['lang'], labels_in_desc=a['labels'], d1=d1, d1_labels=labs,
        text=a['orig'], text0=a['clean'], cats_A=cats_A, cats_B=cats_B, cats_L=cats_L, flags=flags, n_issues=n_issues, lane_key=lane_key,
        mentions={c: len(v) for c, v in acc.items() if lane_map.get(c) in ('HAB', 'PAPER', 'OTHER')},
        severity=[c for c in cats_A if c in SEVERITY], matches=a['matches'],
        acc={c: v for c, v in acc.items()}, bord={c: v for c, v in bord.items()},
    )

def build_label_inference(recs, lane_map, min_share=0.75, min_n=40):
    """Data-driven: a city label (DESCRIPTION1) is used to infer a lane / category only when >= min_share of the
    labelled records that DO have a text-found category fall in that lane / category."""
    by_label = defaultdict(list)
    for r in recs:
        for lab in r['d1_labels']:
            by_label[lab].append(r)
    infer = {}; table = {}
    for lab, rs in by_label.items():
        with_cat = [r for r in rs if r['cats_A']]
        n = len(rs)
        lane_ct = Counter(); cat_ct = Counter()
        for r in rs:
            for l in {lane_map[c] for c in r['cats_A'] if c not in SEVERITY}: lane_ct[l] += 1
            for c in set(r['cats_A']): cat_ct[c] += 1
        table[lab] = dict(n=n, with_cat=len(with_cat), lane_ct=dict(lane_ct), cat_ct=cat_ct.most_common(6), none=sum(1 for r in rs if not r['cats_A']))
        if len(with_cat) < min_n: continue
        top_cat, top_n = (cat_ct.most_common(1) or [(None, 0)])[0]
        if top_cat and top_cat not in UNSPEC and top_n / len(with_cat) >= min_share:
            infer[lab] = [top_cat]; table[lab]['inferred'] = top_cat; table[lab]['inferred_share'] = top_n / len(with_cat)
            continue
        for l in ('HAB', 'PAPER', 'OTHER'):
            if lane_ct[l] / len(with_cat) >= min_share:
                infer[lab] = ['HAB_UNSPECIFIED'] if l == 'HAB' else (['PAPER_UNSPECIFIED'] if l == 'PAPER' else ['OTHER_UNSPECIFIED'])
                table[lab]['inferred'] = infer[lab][0] + ' (lane ' + l + ')'; table[lab]['inferred_share'] = lane_ct[l] / len(with_cat)
                break
    return infer, table

# ---------------------------------------------------------------------------- aggregation
def pct(a, b): return round(100.0 * a / b, 2) if b else 0.0

def cat_counts(recs, cats):
    A = Counter(); B = Counter(); L = Counter(); T = Counter()
    for r in recs:
        for c in r['cats_A']:
            A[c] += 1
            if r['author'] in TENANT_VOICE: T[c] += 1
        for c in r['cats_B']: B[c] += 1
        for c in r['cats_L']: L[c] += 1
    return A, B, L, T

def summarize_population(recs, rules, lane_map):
    n = len(recs)
    A, B, L, T = cat_counts(recs, None)
    ten = [r for r in recs if r['author'] in TENANT_VOICE]
    lane_ct = Counter(r['lane_key'] for r in recs)
    issues_dist = Counter(min(r['n_issues'], 5) for r in recs)
    hab_any = sum(1 for r in recs if 'HAB' in r['lane_key']); paper_any = sum(1 for r in recs if 'PAPER' in r['lane_key'])
    return dict(n=n, n_tenant_voice=len(ten), A=dict(A), B=dict(B), L=dict(L), T=dict(T), lane_ct=dict(lane_ct), issues_dist=dict(issues_dist),
                hab_any=hab_any, paper_any=paper_any, both=sum(1 for r in recs if 'HAB' in r['lane_key'] and 'PAPER' in r['lane_key']))

def cooccurrence(recs, top=25):
    pc = Counter()
    for r in recs:
        cs = [c for c in r['cats_A'] if c not in UNSPEC and c not in SEVERITY]
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)): pc[(cs[i], cs[j])] += 1
    return [(a, b, n) for (a, b), n in pc.most_common(top)]


# ============================================================================ PIPELINE: compare with the old parser, districts, vocabulary

PHONE_RX = re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RX = re.compile(r"https?://\S+|www\.\S+|\b\S+\.(?:com|org|net|gov)\S*", re.I)
TITLE_NAME_RX = re.compile(r"\b(?:Mr|Ms|Mrs|Dr|Miss)\.?\s+[A-Z][a-z]+")
def redact(t):
    t = URL_RX.sub('[link]', t); t = EMAIL_RX.sub('[email]', t); t = PHONE_RX.sub('[phone]', t)
    return TITLE_NAME_RX.sub(lambda m: m.group(0).split()[0] + ' [name]', t)
def safe_example(text):
    """no phone / e-mail / link / titled name, and not a two-capitalised-word run (a likely personal name)"""
    if PHONE_RX.search(text) or EMAIL_RX.search(text) or URL_RX.search(text) or TITLE_NAME_RX.search(text): return False
    if sum(1 for c in text if c.isalpha()) and sum(1 for c in text if c.isupper()) / max(1, sum(1 for c in text if c.isalpha())) < 0.6:
        if re.search(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b", text): return False
    return True

def snippet(text, s, e, pad=70):
    a = max(0, s - pad); b = min(len(text), e + pad)
    return ('…' if a else '') + text[a:s] + '[[' + text[s:e] + ']]' + text[e:b] + ('…' if b < len(text) else '')

# ---------------------------------------------------------------------------- old parser comparison
OLD_MAP = {   # old category -> (kind, targets)  kind 'cat' = new categories, 'rule' = new rule ids
 'NOTICE_EVICTION_DISPLACEMENT': ('cat', ['EVICTION_TERMINATION', 'NOTICE_UNSPECIFIED']),
 'LOCKOUT_UTILITY_SHUTOFF': ('rule', ['LOCK-01', 'UTIL-01', 'UTIL-02', 'UTIL-03', 'UTIL-04', 'UTIL-05', 'UTIL-06', 'WATER-01', 'WATER-04']),
 'RENT_INCREASE_FEES': ('cat', ['RENT_INCREASE_FEES']),
 'RETALIATION_HARASSMENT': ('cat', ['RETALIATION_HARASSMENT']),
 'MOLD_MILDEW': ('cat', ['MOLD_MOISTURE']),
 'PESTS_BEDBUGS': ('cat', ['PESTS']),
 'HEAT': ('cat', ['HEAT']),
 'HOT_WATER': ('cat', ['HOT_WATER']),
 'PLUMBING_DRAIN': ('cat', ['PLUMBING_SEWAGE', 'LEAKS_WATER_INTRUSION']),
 'WATER_INTRUSION_DAMAGE': ('cat', ['LEAKS_WATER_INTRUSION']),
 'ELECTRICAL': ('cat', ['ELECTRICAL']),
 'ELEVATOR': ('cat', ['ELEVATOR_ACCESS']),
 'WINDOW_DOOR_LOCK_SECURITY': ('cat', ['DOORS_WINDOWS_SECURITY']),
 'FIRE_CO_ALARMS_SAFETY': ('cat', ['FIRE_SMOKE_CO_GAS']),
 'CONSTRUCTION_PERMITTING': ('cat', ['CONSTRUCTION_PERMIT']),
 'REPAIR_NONRESPONSE': ('flag', ['MOD_NONRESPONSE']),
 'UNSAFE_UNINHABITABLE': ('sev', ['UNINHABITABLE_SEVERITY']),
 'RELOCATION_ASSISTANCE': ('cat', ['RELOCATION_DISPLACEMENT']),
 'RENTAL_REGISTRATION_INSPECTION': ('cat', ['REGISTRATION_PAPERWORK']),
 'SHA_PUBLIC_HOUSING_CONTEXT': ('flag', ['CONTEXT_SHA']),
}
OLD_LANE = {'NOTICE_EVICTION_DISPLACEMENT': 'PAPER', 'LOCKOUT_UTILITY_SHUTOFF': 'PAPER', 'RENT_INCREASE_FEES': 'PAPER', 'RETALIATION_HARASSMENT': 'PAPER', 'RELOCATION_ASSISTANCE': 'PAPER',
            'RENTAL_REGISTRATION_INSPECTION': 'PAPER', 'REPAIR_NONRESPONSE': 'FLAG', 'SHA_PUBLIC_HOUSING_CONTEXT': 'FLAG', 'CONSTRUCTION_PERMITTING': 'OTHER'}

def load_old_parser(parser_dir):
    import importlib
    if parser_dir and parser_dir not in sys.path: sys.path.insert(0, parser_dir)
    try:
        return importlib.import_module('rare_district_story_parser')
    except Exception as e:
        return None

def compare_with_old(recs, raw_by_id, old_mod, rule_ids_hit):
    """recs: finalised complaint records (with text). returns the per-old-category comparison"""
    pats = old_mod.PATTERNS
    old = {}   # rid -> {cat: [phrases]}
    for r in recs:
        desc = str(raw_by_id[r['id']].get('DESCRIPTION') or '').strip()
        hits = old_mod.matches(desc, pats)
        d = defaultdict(list)
        for h in hits: d[h['category']].append(h['phrase'])
        old[r['id']] = d
    primary = [r for r in recs if not r['review_only']]
    out = []; disag = []      # disag: every record where old and new disagree (all complaints), with record ID
    for pop_key, pop in (('old_primary', primary), ('all_complaints', recs)):
        for ocat, (kind, targets) in OLD_MAP.items():
            n_old = n_new = both = 0; old_only = []; new_only = []; comp = Counter()
            label_only = 0
            for r in pop:
                o = old[r['id']].get(ocat)
                if kind == 'cat': nw = any(c in r['cats_A'] for c in targets)
                elif kind == 'rule': nw = any(t in rule_ids_hit[r['id']] for t in targets)
                elif kind == 'flag': nw = any(c in r['flags'] for c in targets)
                elif kind == 'sev': nw = any(c in r['severity'] for c in targets)
                else: nw = False
                if o: n_old += 1
                if nw: n_new += 1
                if o and nw: both += 1
                if o and not nw: old_only.append((r, o))
                if nw and not o: new_only.append(r)
                if o:
                    for c in r['cats_A']: comp[c] += 1
                    if not r['cats_A']: comp['(none found by new rules)'] += 1
                    if ocat == 'RELOCATION_ASSISTANCE' and all(p.upper() in ('TRAO', 'EDRA') for p in o): label_only += 1
            if pop_key == 'all_complaints':
                for r, ph in old_only:
                    disag.append(dict(old_category=ocat, side='old flagged, new did not', record_id=r['id'], old_phrases='; '.join(sorted(set(ph))[:5]), new_categories=';'.join(r['cats_A']),
                                      new_borderline=';'.join(r['cats_B']), district=r['district'], year=r['year'], authorship=r['author']))
                for r in new_only:
                    disag.append(dict(old_category=ocat, side='new flagged, old did not', record_id=r['id'], old_phrases='', new_categories=';'.join(r['cats_A']),
                                      new_borderline=';'.join(r['cats_B']), district=r['district'], year=r['year'], authorship=r['author']))
            ex_old = sorted([(len(r['text']), r['id'], ph) for r, ph in old_only if safe_example(r['text']) and 25 <= len(r['text']) <= 260], key=lambda x: (abs(x[0] - 100), x[1]))[:4]
            ex_new = sorted([(len(r['text']), r['id']) for r in new_only if safe_example(r['text']) and 25 <= len(r['text']) <= 260], key=lambda x: (abs(x[0] - 100), x[1]))[:4]
            by_id = {r['id']: r for r in pop}
            out.append(dict(pop=pop_key, old_cat=ocat, lane=OLD_LANE.get(ocat, 'HAB'), new_targets=targets, kind=kind, n_pop=len(pop), n_old=n_old, n_new=n_new, both=both,
                            old_only=len(old_only), new_only=len(new_only), label_only=label_only,
                            composition=[(c, k) for c, k in comp.most_common(6)],
                            ex_old=[dict(id=i, phrase=ph if isinstance(ph, str) else ', '.join(sorted(set(ph))[:3]), text=by_id[i]['text'][:260], new=by_id[i]['cats_A']) for _, i, ph in ex_old],
                            ex_new=[dict(id=i, text=by_id[i]['text'][:260], new=by_id[i]['cats_A']) for _, i in ex_new]))
    return out, old, disag

# ---------------------------------------------------------------------------- districts
def two_prop_z(k1, n1, k2, n2):
    if not n1 or not n2: return 0.0
    p = (k1 + k2) / (n1 + n2)
    if p in (0, 1): return 0.0
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (k1 / n1 - k2 / n2) / se if se else 0.0

def district_analysis(recs, profile_cats, min_cell=15):
    D = ['1', '2', '3', '4', '5', '6', '7']
    base = [r for r in recs if r['district'] in D]
    N = len(base)
    n_d = Counter(r['district'] for r in base); n_y = Counter(r['year'] for r in base); n_dy = Counter((r['district'], r['year']) for r in base)
    k_dc = defaultdict(Counter); k_yc = defaultdict(Counter); k_dyc = defaultdict(Counter)
    for r in base:
        for c in set(r['cats_A']):
            k_dc[r['district']][c] += 1; k_yc[r['year']][c] += 1; k_dyc[(r['district'], r['year'])][c] += 1
    years = sorted(n_y)
    std = {d: {} for d in D}; raw = {d: {} for d in D}
    for d in D:
        for c in profile_cats:
            raw[d][c] = 100.0 * k_dc[d][c] / n_d[d] if n_d[d] else 0.0
            tot = 0.0
            for y in years:
                w = n_y[y] / N
                if n_dy[(d, y)] >= min_cell: rate = k_dyc[(d, y)][c] / n_dy[(d, y)]
                else: rate = k_yc[y][c] / n_y[y]
                tot += w * rate
            std[d][c] = 100.0 * tot
    city = {c: 100.0 * sum(k_dc[d][c] for d in D) / N for c in profile_cats}
    pairs = []
    for i in range(len(D)):
        for j in range(i + 1, len(D)):
            a, b = D[i], D[j]
            va = [std[a][c] for c in profile_cats]; vb = [std[b][c] for c in profile_cats]
            dot = sum(x * y for x, y in zip(va, vb)); na = math.sqrt(sum(x * x for x in va)); nb = math.sqrt(sum(y * y for y in vb))
            cos = dot / (na * nb) if na and nb else 0
            mad = sum(abs(x - y) for x, y in zip(va, vb)) / len(va)
            rows = []
            for c in profile_cats:
                z = two_prop_z(k_dc[a][c], n_d[a], k_dc[b][c], n_d[b])
                rows.append(dict(cat=c, a_std=round(std[a][c], 2), b_std=round(std[b][c], 2), a_raw=round(raw[a][c], 2), b_raw=round(raw[b][c], 2),
                                 a_n=k_dc[a][c], b_n=k_dc[b][c], diff=round(std[a][c] - std[b][c], 2), z=round(z, 2)))
            alike = sorted([x for x in rows if city[x['cat']] >= 2.0], key=lambda x: (abs(x['diff']), -city[x['cat']]))[:4]
            diff = sorted(rows, key=lambda x: -abs(x['z']))[:4]
            pairs.append(dict(a=a, b=b, cosine=round(cos, 4), mad_pp=round(mad, 3), alike=alike, different=diff))
    sig = {}
    for d in D:
        rows = []
        for c in profile_cats:
            k1 = k_dc[d][c]; n1 = n_d[d]; k2 = sum(k_dc[x][c] for x in D if x != d); n2 = N - n1
            rows.append(dict(cat=c, rate=round(raw[d][c], 2), others=round(100.0 * k2 / n2, 2), z=round(two_prop_z(k1, n1, k2, n2), 2)))
        sig[d] = dict(higher=sorted([x for x in rows if x['z'] > 0], key=lambda x: -x['z'])[:4], lower=sorted([x for x in rows if x['z'] < 0], key=lambda x: x['z'])[:4])
    table = [dict(district=d, n=n_d[d], rates={c: round(raw[d][c], 2) for c in profile_cats}, std={c: round(std[d][c], 2) for c in profile_cats},
                  years=dict(sorted(Counter(r['year'] for r in base if r['district'] == d).items()))) for d in D]
    unk = [r for r in recs if r['district'] not in D]
    return dict(districts=D, n_city=N, n_unknown=len(unk), cats=profile_cats, city={c: round(city[c], 2) for c in profile_cats}, table=table, pairs=pairs, signature=sig)

# ---------------------------------------------------------------------------- vocabulary pieces
MISSPELL = {
 'landlord': ['lanlord', 'landord', 'lanldord', 'landloard', 'landlored', 'landlard', 'ladlord', 'landdlord'],
 'tenant': ['tennant', 'tentant', 'tenent', 'tenat', 'tennants', 'tenents'],
 'complainant': ['complaintant', 'complainaint', 'complanint', 'complanant', 'complaiant', 'complainanat'],
 'management': ['managment', 'mangement', 'managemnt', 'manangement'],
 'apartment': ['appartment', 'aprtment', 'apatments', 'appartments'],
 'furnace': ['furnance'], 'electrical': ['eletrical', 'electical', 'electrial'], 'electricity': ['electricty', 'eletricity', 'electicity', 'elctricity'],
 'wiring': ['wireing'], 'plumbing': ['pluming', 'plumbng'], 'toilet': ['toliet', 'tolet'],
 'infestation': ['infestion', 'investation', 'infestatin', 'intestation'], 'cockroach': ['cochroach', 'coackroach', 'cokroaches', 'cocroaches', 'cockroches'],
 'ceiling': ['celing', 'cieling', 'celling'], 'ventilation': ['ventillation', 'ventalation'],
 'maintenance': ['maintenace', 'maintence', 'maintenence', 'maintanence', 'maintainance', 'maintance', 'mainenance'],
 'uninhabitable': ['unhabitable', 'unihabitable'], 'hazard': ['hazzard'], 'eviction': ['eviciton', 'evction', 'evection', 'eveiction'],
 'retaliation': ['retailiation', 'retalitation', 'retaltion'], 'harassment': ['harrassment', 'harrasment'], 'illegal': ['illigal', 'illeagal', 'ilegal'],
 'assistance': ['assitance'], 'notice': ['noitce'], 'basement': ['basment', 'bassment'], 'kitchen': ['kithcen', 'ktichen', 'kichen'], 'unresponsive': ['unresposive', 'unrepsonsive', 'unreponsive'],
 'sewage': ['sweage', 'sewege', 'sewge'], 'mildew': ['mildrew'], 'bathroom': ['bathrm', 'bathroon'],
}
SHORTHAND = [   # (pattern, case-sensitive, meaning, how known)
 (r"\bmgmt\b", False, 'management', 'self-evident abbreviation'), (r"\bmgr\b", False, 'manager', 'self-evident abbreviation'), (r"\bmgt\b", False, 'management', 'self-evident abbreviation'),
 (r"\bcompl\b", False, 'complainant', 'inferred from use'), (r"\bLL\b", True, 'landlord', 'inferred from use'), (r"\bw/o\b", False, 'without', 'self-evident abbreviation'),
 (r"\bb/c\b", False, 'because', 'self-evident abbreviation'), (r"\bapt\b", False, 'apartment', 'self-evident abbreviation'), (r"\bbldg\b", False, 'building', 'self-evident abbreviation'),
 (r"\bH/Z\b", True, 'housing / zoning inspector', 'inferred from use'), (r"\bHZT\b", True, 'staff note label (housing / zoning team?)', 'not verified'), (r"\bHZW\b", True, 'staff case label', 'not verified'),
 (r"\bNOV\b", True, 'notice of violation', 'SDCI term'), (r"\bPOV\b", True, 'pay or vacate (notice)', 'inferred from use'), (r"\bNTQ\b", True, 'notice to quit', 'inferred from use'),
 (r"\bCSB\b", True, 'Customer Service Bureau (intake)', 'inferred from use'), (r"\bSFD\b", True, 'Seattle Fire Department', 'self-evident'), (r"\bSPD\b", True, 'Seattle Police Department', 'self-evident'),
 (r"\bPSE\b", True, 'Puget Sound Energy', 'self-evident'), (r"\bHBMC\b", True, 'Housing and Building Maintenance Code', 'SDCI term'), (r"\bRRIO\b", True, 'Rental Registration and Inspection Ordinance', 'SDCI term'),
 (r"\bTRAO\b", True, 'Tenant Relocation Assistance Ordinance', 'named in the record text'), (r"\bEDRA\b", True, 'Economic Displacement Relocation Assistance', 'inferred, not verified'),
 (r"\bJCEO\b", True, 'Just Cause Eviction Ordinance', 'named in the record text'), (r"\bPOTA\b", True, 'city intake label (tenant-assistance team)', 'not verified'), (r"\bRARO\b", True, 'Rental Agreement Regulation Ordinance', 'inferred, not verified'),
 (r"\bROFR\b", True, 'right of first refusal', 'self-evident'), (r"\bMFTE\b", True, 'Multifamily Tax Exemption (income-restricted units)', 'inferred, not verified'), (r"\bADU\b|\bDADU\b", True, 'accessory / detached accessory dwelling unit', 'self-evident'),
 (r"\bSRO\b", True, 'single room occupancy', 'self-evident'), (r"\bESA\b", True, 'emotional support animal', 'inferred from use'), (r"\bHVAC\b", True, 'heating / ventilation / air conditioning', 'self-evident'),
 (r"\bSR\s*#?\s*\d", True, 'service request number', 'inferred from use'), (r"\bL/T\b", True, 'landlord / tenant', 'self-evident'), (r"\bPM\b", True, 'property manager', 'inferred from use'),
 (r"\bSHA\b", True, 'Seattle Housing Authority', 'self-evident'), (r"\bUNIT\s*#?\s*\d", True, 'unit number', 'self-evident'),
]


# ============================================================================ PIPELINE: examples, vocabulary tables, data bundle, writers
def norm_phrase(p):
    p = re.sub(r"\s+", " ", p.lower()).strip(" ,.;:-()\"'")
    return p[:80]

def pick_rule_examples(recs, rules):
    """one verbatim example per rule (and per kind of rejection) taken from the real records"""
    best_a = {}; best_b = {}; rej = {}
    for r in recs:
        txt = r['text']
        L = len(txt)
        safe = None
        for m in r['matches']:
            d = m['decision']
            if d in ('ACCEPT', 'BORDERLINE'):
                tgt = best_a if d == 'ACCEPT' else best_b
                if not (25 <= L <= 260):
                    sc_len = 400 + abs(L - 100)
                else:
                    sc_len = abs(L - 100)
                if safe is None: safe = safe_example(txt)
                score = (0 if safe else 1000) + sc_len + (0 if r['author'] in TENANT_VOICE + ('NEUTRAL_UNATTRIBUTED',) else 15) + (0 if r['text0'] == txt else 300)
                cur = tgt.get(m['rule'])
                if cur is None or score < cur[0] or (score == cur[0] and r['id'] < cur[1]):
                    tgt[m['rule']] = (score, r['id'], m['phrase'], txt, snippet(txt, m['start'], m['end'], 60), m.get('obj', ''), m.get('cue', ''), safe)
            elif d.startswith('REJECT'):
                key = (m['rule'], d)
                if safe is None: safe = safe_example(txt)
                score = (0 if safe else 1000) + (abs(L - 100) if 25 <= L <= 260 else 500)
                cur = rej.get(key)
                if cur is None or score < cur[0] or (score == cur[0] and r['id'] < cur[1]):
                    rej[key] = (score, r['id'], m['phrase'], txt, snippet(txt, m['start'], m['end'], 60), m['reason'], safe)
    out = {}
    for rule in rules:
        a = best_a.get(rule.id); b = best_b.get(rule.id)
        out[rule.id] = dict(
            accept=dict(id=a[1], phrase=a[2], text=a[3], snippet=a[4], obj=a[5], cue=a[6], safe=a[7]) if a else None,
            borderline=dict(id=b[1], phrase=b[2], text=b[3], snippet=b[4], safe=b[7]) if b else None)
    rejs = [dict(rule=k[0], decision=k[1], id=v[1], phrase=v[2], text=v[3], snippet=v[4], reason=v[5], safe=v[6]) for k, v in rej.items()]
    return out, rejs

def term_tables(recs):
    cnt = Counter(); first = {}
    for r in recs:
        seen = set()
        for m in r['matches']:
            if m['decision'] not in ('ACCEPT', 'BORDERLINE'): continue
            key = (m['cat'], m['rule'], m['decision'], norm_phrase(m['phrase']))
            if key in seen: continue
            seen.add(key); cnt[key] += 1
            L = len(r['text'])
            sc = (0 if 25 <= L <= 260 else 500) + abs(L - 100)
            if key not in first or sc < first[key][0]:
                first[key] = (sc, r['id'], snippet(r['text'], m['start'], m['end'], 55))
    rows = []
    for key, n in cnt.items():
        cat, rule, dec, ph = key
        rows.append(dict(category=cat, rule=rule, decision=dec, phrase=ph, records=n, example_id=first[key][1], example=first[key][2]))
    rows.sort(key=lambda x: (x['category'], -x['records'], x['phrase']))
    return rows

def count_regex_records(patterns, texts_by_id, flags=re.I, limit_examples=1):
    """patterns: list of (label, regex-object). returns {label: (records, example_id, example_text)}"""
    out = {}
    for lab, rx_ in patterns:
        n = 0; ex = None
        for rid, t in texts_by_id.items():
            m = rx_.search(t)
            if m:
                n += 1
                if ex is None or (25 <= len(t) <= 220 and (len(ex[1]) > 220 or len(ex[1]) < 25)): ex = (rid, snippet(t, m.start(), m.end(), 60))
        out[lab] = (n, ex)
    return out

def vocabulary_extras(texts_by_id, gm, recs):
    tok = re.compile(r"[A-Za-z']+")
    var2canon = {v.lower(): canon for canon, vs in MISSPELL.items() for v in vs}
    mcount = Counter(); mex = {}; gcount = Counter(); gex = {}
    def upd(store, key, rid, t, m):
        sc = (0 if 25 <= len(t) <= 220 else 500) + abs(len(t) - 100)
        cur = store.get(key)
        if cur is None or sc < cur[0] or (sc == cur[0] and rid < cur[1]):
            store[key] = (sc, rid, snippet(t, m.start(), m.end(), 60))
    for rid, t in texts_by_id.items():
        seen_m = set(); seen_g = set()
        for m in tok.finditer(t):
            w = m.group(0).lower()
            if w in var2canon and w not in seen_m:
                seen_m.add(w); mcount[w] += 1; upd(mex, w, rid, t, m)
            if w in gm and w not in seen_g:
                seen_g.add(w); gcount[w] += 1; upd(gex, w, rid, t, m)
    misspell = [dict(canonical=var2canon[w], variant=w, records=n, example_id=mex[w][1], example=mex[w][2]) for w, n in mcount.items()]
    misspell.sort(key=lambda x: (-x['records'], x['canonical']))
    # shorthand (about 40 patterns)
    short = []
    for rx_, cs, mean, how in SHORTHAND:
        cre = re.compile(rx_, 0 if cs else re.I)
        n = 0; best = None
        for rid, t in texts_by_id.items():
            m = cre.search(t)
            if m:
                n += 1
                sc = (0 if 25 <= len(t) <= 220 else 500) + abs(len(t) - 100)
                if best is None or sc < best[0] or (sc == best[0] and rid < best[1]): best = (sc, rid, snippet(t, m.start(), m.end(), 60))
        if n: short.append(dict(token=re.sub(r"\\b|\\s\*|#\?|\\d|\\", "", rx_).replace('|', ' / '), meaning=mean, how_known=how, records=n, example_id=best[1], example=best[2]))
    short.sort(key=lambda x: -x['records'])
    fused = [dict(fused_token=w, split='%s %s' % (gm[w][0], gm[w][1]), records=n, example_id=gex[w][1], example=gex[w][2]) for w, n in gcount.items()]
    fused.sort(key=lambda x: -x['records'])
    return misspell, short, fused

def authorship_table(recs, glue_by_id):
    eras = [('2003-2008', 2003, 2008), ('2009-2014', 2009, 2014), ('2015-2019', 2015, 2019), ('2020-2022', 2020, 2022), ('2023-2025', 2023, 2025)]
    n = len(recs)
    by = defaultdict(list)
    for r in recs: by[r['author']].append(r)
    rows = []
    for cls, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        era_pct = {}
        for nm, a, b in eras:
            pool = [r for r in recs if a <= r['year'] <= b]
            era_pct[nm] = pct(sum(1 for r in pool if r['author'] == cls), len(pool))
        ex = None
        cand = sorted([r for r in rs if safe_example(r['text']) and 30 <= len(r['text']) <= 220], key=lambda r: (abs(len(r['text']) - 110), r['id']))
        if cand: ex = dict(id=cand[0]['id'], text=cand[0]['text'])
        glue = sum(1 for r in rs if glue_by_id.get(r['id']))
        rows.append(dict(cls=cls, label=AUTHOR_LABEL.get(cls, cls), n=len(rs), pct=pct(len(rs), n), era=era_pct, glue_pct=pct(glue, len(rs)), example=ex))
    return rows, [e[0] for e in eras]

def label_table(recs, label_info, lane_map):
    rows = []
    for lab, t in sorted(label_info.items(), key=lambda kv: -kv[1]['n']):
        if t['n'] < 40: continue
        n = t['n']; lc = t['lane_ct']
        ex = None
        cand = sorted([r for r in recs if lab in r['d1_labels'] and safe_example(r['text']) and 30 <= len(r['text']) <= 200], key=lambda r: (abs(len(r['text']) - 100), r['id']))
        if cand: ex = dict(id=cand[0]['id'], d1=cand[0]['d1'][:90], text=cand[0]['text'])
        rows.append(dict(label=lab, n=n, pct_hab=pct(lc.get('HAB', 0), n), pct_paper=pct(lc.get('PAPER', 0), n), pct_other=pct(lc.get('OTHER', 0), n), pct_none=pct(t['none'], n),
                         top=[(c, pct(k, n)) for c, k in t['cat_ct']], inferred=t.get('inferred', ''), inferred_share=round(100 * t.get('inferred_share', 0), 1) if t.get('inferred') else '', example=ex))
    return rows


# ============================================================================ PIPELINE: data bundle for the HTML page
def R_(t, n=None):
    t = redact(t or '')
    return t if n is None else t[:n]

def build_data(B, out_name):
    f = B['findings']; recs = B['recs']; n_all = len(recs)
    rng = random.Random(20261017)
    lane_label = {'HAB': 'Habitability', 'PAPER': 'Paperwork / landlord-tenant', 'OTHER': 'Other SDCI / not housing', 'FLAG': 'Flag'}
    cats = [dict(c) for c in B['cat_rows']]
    # lane summary (whole population)
    lk = Counter(r['lane_key'] for r in recs)
    lane_summary = [dict(key=k, n=v, pct=pct(v, n_all)) for k, v in sorted(lk.items(), key=lambda kv: -kv[1])]
    iss = Counter(min(r['n_issues'], 5) for r in recs if r['n_issues'] > 0)
    issues_hist = [dict(k=('5+' if k == 5 else str(k)), n=iss[k], pct=pct(iss[k], sum(iss.values()))) for k in sorted(iss)]
    cooc = [dict(a=a, b=b, a_label=CAT_LABEL.get(a, a), b_label=CAT_LABEL.get(b, b), n=n) for a, b, n in B['cooc']]
    # old comparison
    cmp_rows = []
    for c in B['cmp_rows']:
        cc = dict(c)
        cc['ex_old'] = [dict(id=e['id'], phrase=e['phrase'], text=R_(e['text']), new=e['new']) for e in c['ex_old']]
        cc['ex_new'] = [dict(id=e['id'], text=R_(e['text']), new=e['new']) for e in c['ex_new']]
        cmp_rows.append(cc)
    # rules (page copy)
    rr = []
    for r in B['rule_rows']:
        x = dict(r)
        x['example_text'] = R_(x['example_text']); x['borderline_example'] = R_(x['borderline_example'])
        rr.append(x)
    # borderline sample: up to 12 per category
    by_cat = defaultdict(list)
    for p in B['pocket']: by_cat[p['category']].append(p)
    pocket_counts = sorted([(c, len(v)) for c, v in by_cat.items()], key=lambda kv: -kv[1])
    sample = []
    for c, v in by_cat.items():
        sub = rng.sample(v, min(10, len(v)))
        for p in sub: sample.append(dict(id=p['record_id'], cat=p['category'], label=p['label'], rule=p['rule'], phrase=p['phrase'], reason=p['reason'], text=R_(p['text'], 330), district=p['district'], year=p['year']))
    sample.sort(key=lambda x: (x['cat'], x['id']))
    # unmatched
    um_ct = Counter(u['author'] for u in B['unmatched'])
    um_sample = [dict(id=u['record_id'], author=u['author'], labels=u['city_labels'], text=R_(u['text'], 300)) for u in rng.sample(B['unmatched'], min(70, len(B['unmatched'])))]
    # rejects
    rej_examples = [dict(rule=e['rule'], decision=e['decision'], id=e['id'], phrase=e['phrase'], snippet=R_(e['snippet']), reason=e['reason']) for e in B['rej_ex'] if e['decision'] in ('REJECT_NEGATED', 'REJECT_CONTEXT', 'REJECT_OVERLAP')]
    rej_examples.sort(key=lambda e: (e['decision'], e['rule']))
    # labels
    labs = []
    for l in B['labels']:
        x = dict(l)
        if x.get('example'): x['example'] = dict(id=x['example']['id'], d1=x['example']['d1'], text=R_(x['example']['text']))
        labs.append(x)
    auth = []
    for a in B['auth_rows']:
        x = dict(a)
        if x.get('example'): x['example'] = dict(id=x['example']['id'], text=R_(x['example']['text']))
        auth.append(x)
    ms = [dict(m, example=R_(m['example'])) for m in B['misspell'][:80]]
    sh = [dict(m, example=R_(m['example'])) for m in B['short']]
    fu = [dict(m, example=R_(m['example'])) for m in B['fused'][:140]]
    inf = [dict(m, example=R_(m['example'])) for m in sorted(B['informal'], key=lambda x: -x['records'])[:90]]
    dist = B['dist']
    data = dict(
        meta=dict(title='Landlord-tenant complaint vocabulary audit', built=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), version=VERSION, input_file=os.path.basename(B['json_path']), sha256=B['sha'],
                  rows=f['n_rows'], complaints=f['n_complaints'], with_text=f['n_complaints_text'], date_min=f['date_min'], date_max=f['date_max'], rules=len(B['rules']), out=out_name,
                  glue_repairs=len(B['gm'])),
        findings=f, cats=cats, lane_summary=lane_summary, issues_hist=issues_hist, cooc=cooc, authorship=auth, eras=B['eras'], labels=labs, rules=rr, misspell=ms, shorthand=sh, fused=fu, informal=inf,
        compare=cmp_rows, pocket_counts=pocket_counts, pocket_sample=sample, pocket_total=len(B['pocket']), unmatched_counts=dict(um_ct), unmatched_total=len(B['unmatched']), unmatched_sample=um_sample,
        reject_examples=rej_examples, districts=dist, cat_label=CAT_LABEL, author_label=AUTHOR_LABEL, lane_label=lane_label,
        lane_summary_labels={'HAB': 'Habitability only', 'PAPER': 'Paperwork only', 'HAB+PAPER': 'Both habitability and paperwork', 'OTHER': 'Other SDCI / not housing only',
                              'HAB+OTHER': 'Habitability + other SDCI', 'OTHER+PAPER': 'Paperwork + other SDCI', 'HAB+OTHER+PAPER': 'Habitability + paperwork + other SDCI', 'INQUIRY_ONLY': 'Information request only (no issue stated)',
                              'STAFF_NOTE_ONLY': 'Staff note only (TRAO / label)', 'UNCONFIRMED': 'Unconfirmed (borderline or label-inferred only)', 'NO_ISSUE_WORDS': 'No issue words found'},
    )
    return data

def write_html(B, out_dir, out_name, template):
    data = build_data(B, out_name)
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html_text = template.replace('/*__DATA__*/null', js)
    p = os.path.join(out_dir, out_name)
    with open(p, 'w', encoding='utf-8') as f: f.write(html_text)
    return p, len(html_text)


# ============================================================================ PIPELINE: orchestration and writers

def write_csv(path, rows, fields):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows: w.writerow(r)

def self_test(rules, examples, analyze_fn):
    """every rule must reproduce its own embedded, verbatim example"""
    res = {}
    for rule in rules:
        ex = examples.get(rule.id)
        if not ex:
            res[rule.id] = 'NO_EXAMPLE'; continue
        a = analyze_fn(ex['text'], {})
        ok = any(m['rule'] == rule.id and m['decision'] in ('ACCEPT', 'BORDERLINE') for m in a['matches'])
        res[rule.id] = 'PASS' if ok else 'FAIL'
    return res

def run_all(json_path, out_dir, parser_dir, decisions_path=None, workers=None, examples=None):
    t0 = time.time()
    def log(*a): print('[%5.0fs]' % (time.time() - t0), *a, flush=True)
    os.makedirs(out_dir, exist_ok=True)
    log('loading', json_path)
    data = load_records(json_path)
    sha = sha256_file(json_path)
    complaints = [r for r in data if str(r.get('RECORDTYPE', '')).upper() == 'COMPLAINT']
    with_text = [r for r in complaints if clean(r.get('DESCRIPTION'))]
    raw_by_id = {r['RECORDNUM']: r for r in complaints}
    type_counts = Counter(str(r.get('RECORDTYPE', '')).upper() for r in data)
    years = [str(r.get('OPENDATE'))[:10] for r in data if r.get('OPENDATE')]
    log('rows', len(data), 'complaints', len(complaints), 'with text', len(with_text))
    texts0 = [clean(r['DESCRIPTION']) for r in with_text]
    gm = build_glue_map(texts0)
    log('fused-word repairs learned from the records:', len(gm))
    rules = RULES
    lane_map = {r.cat: r.lane for r in rules}
    lane_map.update({'PAPER_UNSPECIFIED': 'PAPER', 'OTHER_UNSPECIFIED': 'OTHER'})
    log('analysing', len(with_text), 'descriptions with', len(rules), 'rules')
    analysis = run_analysis(with_text, gm, workers)
    decisions = {}
    if decisions_path and os.path.exists(decisions_path):
        with open(decisions_path, encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                dcs = (row.get('decision') or '').strip().upper()
                if dcs in ('ACCEPT', 'REJECT'): decisions[(row['record_id'].strip(), row['category'].strip())] = dcs
        log('manual decisions applied:', len(decisions))
    recs0 = [finalize_record(raw_by_id[k], analysis[k], rules, lane_map, decisions, None) for k in analysis]
    label_infer, label_info = build_label_inference(recs0, lane_map)
    recs = [finalize_record(raw_by_id[k], analysis[k], rules, lane_map, decisions, label_infer) for k in analysis]
    recs.sort(key=lambda r: r['id'])
    by_id = {r['id']: r for r in recs}
    log('records finalised')

    # ---- populations and headline numbers
    n_all = len(recs)
    pop_all = summarize_population(recs, rules, lane_map)
    old_primary_all = [r for r in complaints if not truth(r.get('LLT_REVIEW_ONLY'))]
    prim_recs = [r for r in recs if not r['review_only']]
    rev_recs = [r for r in recs if r['review_only']]
    pop_prim = summarize_population(prim_recs, rules, lane_map); pop_rev = summarize_population(rev_recs, rules, lane_map)
    ten = [r for r in recs if r['author'] in TENANT_VOICE]
    spec_cats = [c for c in CAT_LABEL if lane_map.get(c) in ('HAB', 'PAPER', 'OTHER') and c not in UNSPEC and c not in SEVERITY]

    # ---- category table
    cat_rows = []
    for cat, lab in CAT_LABEL.items():
        ln = lane_map.get(cat)
        if ln is None: continue
        a = pop_all['A'].get(cat, 0); b = pop_all['B'].get(cat, 0); l = pop_all['L'].get(cat, 0); t = pop_all['T'].get(cat, 0)
        rev = sum(1 for r in rev_recs if cat in r['cats_A']) if ln != 'FLAG' else sum(1 for r in rev_recs if cat in r['flags'])
        if ln == 'FLAG':
            a = sum(1 for r in recs if cat in r['flags']); t = sum(1 for r in ten if cat in r['flags'])
        cat_rows.append(dict(cat=cat, label=lab, lane=ln, nA=a, pctA=pct(a, n_all), nT=t, pctT=pct(t, len(ten)), nB=b, nL=l, nIncl=a + b + l, in_review_only=rev, pct_in_review_only=pct(rev, a)))
    # ---- authorship
    glue_re = re.compile(r"[A-Za-z]{7,30}")
    glue_by_id = {k: any(w.lower() in gm for w in glue_re.findall(clean(raw_by_id[k]['DESCRIPTION']))) for k in analysis}
    auth_rows, eras = authorship_table(recs, glue_by_id)
    # ---- city labels
    labels = label_table(recs, label_info, lane_map)
    # ---- rule stats and examples
    rule_stats = defaultdict(lambda: Counter())
    rule_ids_hit = defaultdict(set)
    for r in recs:
        seen = set()
        for m in r['matches']:
            k = (m['rule'], m['decision'])
            if k not in seen: rule_stats[m['rule']][m['decision']] += 1; seen.add(k)
            if m['decision'] == 'ACCEPT': rule_ids_hit[r['id']].add(m['rule'])
    auto_ex, rej_ex = pick_rule_examples(recs, rules)
    st = self_test(rules, examples or {}, analyze) if examples else {}
    rule_rows = []
    for rule in rules:
        s = rule_stats[rule.id]
        emb = (examples or {}).get(rule.id)
        a = auto_ex[rule.id]
        rule_rows.append(dict(id=rule.id, lane=rule.lane, cat=rule.cat, cat_label=CAT_LABEL.get(rule.cat, rule.cat), kind=rule.kind, desc=rule.desc, pattern=rule.pat, cue=rule.cue_pat or '', cue2=rule.cue2_pat or '', window=rule.win if rule.kind == 'COMPOUND' else '',
                              priority=rule.prio, records_accept=s['ACCEPT'], records_borderline=s['BORDERLINE'], rejected_negated=s['REJECT_NEGATED'], rejected_overlap=s['REJECT_OVERLAP'], rejected_context=s['REJECT_CONTEXT'],
                              example_id=(emb['id'] if emb else (a['accept']['id'] if a['accept'] else (a['borderline']['id'] if a['borderline'] else ''))),
                              example_text=(emb['text'] if emb else (a['accept']['text'] if a['accept'] else (a['borderline']['text'] if a['borderline'] else ''))),
                              example_phrase=(emb['phrase'] if emb else (a['accept']['phrase'] if a['accept'] else (a['borderline']['phrase'] if a['borderline'] else ''))),
                              example_decision=('ACCEPT' if (emb and emb.get('decision') == 'ACCEPT') or (not emb and a['accept']) else 'BORDERLINE'),
                              example_source='embedded in script' if emb else 'auto-picked this run', self_test=st.get(rule.id, 'n/a'),
                              borderline_example_id=(a['borderline']['id'] if a['borderline'] else ''), borderline_example=(a['borderline']['snippet'] if a['borderline'] else '')))
    # ---- vocabulary
    texts_by_id = {k: clean(raw_by_id[k]['DESCRIPTION']) for k in analysis}
    misspell, short, fused = vocabulary_extras(texts_by_id, gm, recs)
    terms = term_tables(recs)
    informal = [t for t in terms if t['category'] in ('INFORMAL_SLANG', 'PROFANITY_OR_INSULT')]
    lang_ct = Counter(r['lang'] for r in recs)
    log('vocabulary tables built')
    # ---- old parser comparison
    old_mod = load_old_parser(parser_dir)
    cmp_rows = []; old_by_id = {}; disag = []
    if old_mod:
        cmp_rows, old_by_id, disag = compare_with_old(recs, raw_by_id, old_mod, rule_ids_hit)
        log('compared with the old parser')
    # ---- districts
    dist = district_analysis(recs, [c for c in spec_cats if pop_all['A'].get(c, 0) >= 100])
    # ---- borderline pocket and unmatched
    pocket = []
    for r in recs:
        for c in r['cats_B']:
            ms = r['bord'].get(c, [])
            ph = ' | '.join(sorted({norm_phrase(m['phrase']) for m in ms})[:3])
            why = ms[0]['reason'] if ms else ''
            pocket.append(dict(record_id=r['id'], category=c, label=CAT_LABEL.get(c, c), rule=ms[0]['rule'] if ms else '', phrase=ph, reason=why, district=r['district'], year=r['year'], author=r['author'],
                               text=r['text'], suggested_decision='', decision=''))
        for c in r['cats_L']:
            pocket.append(dict(record_id=r['id'], category=c, label=CAT_LABEL.get(c, c), rule='city label', phrase=','.join(r['d1_labels']), reason='no issue wording in the text; category inferred only from the city label in DESCRIPTION1',
                               district=r['district'], year=r['year'], author=r['author'], text=r['text'], suggested_decision='', decision=''))
    unmatched = [dict(record_id=r['id'], year=r['year'], district=r['district'], author=r['author'], channel=r['channel'], city_labels=','.join(r['d1_labels']), text=r['text'])
                 for r in recs if r['lane_key'] == 'NO_ISSUE_WORDS']
    # ---- findings about the old script
    hab_recs = [r for r in recs if 'HAB' in r['lane_key']]
    findings = dict(
        n_rows=len(data), n_complaints=len(complaints), n_complaints_text=n_all, n_old_primary=len(old_primary_all), n_review_only=sum(1 for r in complaints if truth(r.get('LLT_REVIEW_ONLY'))),
        n_noncomplaint=len(data) - len(complaints), type_counts=dict(type_counts), hab_total=len(hab_recs), hab_in_review_only=sum(1 for r in hab_recs if r['review_only']),
        workflow=sum(1 for r in recs if r['author'] == 'STAFF_WORKFLOW_NOTE'), label_only=sum(1 for r in recs if r['author'] == 'STAFF_LABEL_ONLY'),
        tenant_voice=len(ten), tenant_with_issue=sum(1 for r in ten if r['cats_A']), tenant_inquiry_only=sum(1 for r in ten if r['lane_key'] == 'INQUIRY_ONLY'),
        no_issue=sum(1 for r in recs if r['lane_key'] == 'NO_ISSUE_WORDS'), inquiry_only=sum(1 for r in recs if r['lane_key'] == 'INQUIRY_ONLY'),
        lang=dict(lang_ct), blank_text=len(complaints) - n_all,
        date_min=min(years) if years else '', date_max=max(years) if years else '',
        vi_text_dup=None)
    # NOV records repeat complaint text?
    ctext = set(texts0)
    vi = [r for r in data if str(r.get('RECORDTYPE', '')).upper() == 'NOTICE OF VIOLATION' and clean(r.get('DESCRIPTION'))]
    findings['vi_n'] = len(vi); findings['vi_text_equals_a_complaint'] = sum(1 for r in vi if clean(r['DESCRIPTION']) in ctext)
    findings['desc_with_linebreak'] = sum(1 for r in complaints if re.search(r'[\r\n]', str(r.get('DESCRIPTION') or '')))
    rep = Counter((r['address'], str(r['opendate'])[:10], r['text']) for r in recs if r['address'])
    findings['repeat_groups'] = sum(1 for v in rep.values() if v > 1); findings['repeat_records'] = sum(v for v in rep.values() if v > 1)
    # what do "N-day notice" phrases refer to? (words within 90 characters of the phrase; a record can fall in more than one group)
    nd_rx = re.compile(r"\b(?:\d{1,3}|three|ten|fourteen|twenty|thirty|sixty|ninety)\s*-?\s*days?\s*(?:written\s+)?notices?\b", re.I)
    nd_k = {'evict': re.compile(r"evict|vacate|terminat|move\s*out|pay\s+or|quit|leave", re.I),
            'incr': re.compile(r"rent\s+increase|increase\s+(?:in|of)\s+(?:the\s+)?rent|raise\s+(?:the\s+|my\s+)?rent|rent\s+hike|increase", re.I),
            'entry': re.compile(r"\benter|\bentry\b|inspect|access\s+to\s+(?:the\s+)?unit", re.I),
            'repair': re.compile(r"repair|construction|renovat|remodel|work\s+in\s+(?:the\s+)?unit", re.I)}
    nd = dict(total=0, evict=0, incr=0, entry=0, repair=0, none=0)
    for r in recs:
        m = nd_rx.search(r['text'])
        if not m: continue
        w = r['text'][max(0, m.start() - 90):m.end() + 90]
        nd['total'] += 1; got = [k for k, x in nd_k.items() if x.search(w)]
        for k in got: nd[k] += 1
        if not got: nd['none'] += 1
    findings['nday'] = nd

    bundle = dict(recs=recs, by_id=by_id, rules=rules, rule_rows=rule_rows, cat_rows=cat_rows, pop_all=pop_all, pop_prim=pop_prim, pop_rev=pop_rev, auth_rows=auth_rows, eras=eras, labels=labels, label_infer=label_infer,
                  misspell=misspell, short=short, fused=fused, terms=terms, informal=informal, cmp_rows=cmp_rows, dist=dist, pocket=pocket, unmatched=unmatched, findings=findings, rej_ex=rej_ex,
                  gm=gm, sha=sha, json_path=json_path, spec_cats=spec_cats, raw_by_id=raw_by_id, cooc=cooccurrence(recs), lane_map=lane_map, old_by_id=old_by_id, disag=disag, t0=t0)
    write_outputs(bundle, out_dir, log)
    return bundle

def write_outputs(B, out_dir, log):
    recs = B['recs']; rule_rows = B['rule_rows']
    # record-level
    rows = []
    for r in recs:
        rows.append(dict(record_id=r['id'], opendate=r['opendate'], year=r['year'], district=r['district'], record_type_desc=r['tdesc'], review_only=r['review_only'], llt_group=r['group'], status=r['status'], address=r['address'],
                         authorship=r['author'], channel=r['channel'], language=r['lang'], city_labels_in_description1=','.join(r['d1_labels']), labels_inside_description=','.join(r['labels_in_desc']),
                         lane=r['lane_key'], distinct_issues=r['n_issues'], categories_text_evidence=';'.join(r['cats_A']), categories_borderline_only=';'.join(r['cats_B']),
                         categories_label_inferred_only=';'.join(r['cats_L']), flags=';'.join(r['flags']), mentions=';'.join('%s=%d' % (c, n) for c, n in sorted(r['mentions'].items())),
                         description=r['text'], description1=r['d1']))
    write_csv(os.path.join(out_dir, 'record_issues.csv'), rows, list(rows[0].keys()))
    # match-level audit (every match and every rejection)
    n = 0
    with open(os.path.join(out_dir, 'match_audit.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['record_id', 'district', 'year', 'authorship', 'lane', 'category', 'rule', 'rule_kind', 'decision', 'reason', 'matched_phrase', 'object_term', 'cue_term', 'start', 'end', 'context'])
        for r in recs:
            for m in r['matches']:
                w.writerow([r['id'], r['district'], r['year'], r['author'], m['lane'], m['cat'], m['rule'], m['kind'], m['decision'], m['reason'], m['phrase'], m.get('obj', ''), m.get('cue', ''), m['start'], m['end'], snippet(r['text'], m['start'], m['end'], 60)])
                n += 1
    log('match_audit rows', n)
    flds = ['id', 'lane', 'cat', 'cat_label', 'kind', 'desc', 'pattern', 'cue', 'cue2', 'window', 'priority', 'records_accept', 'records_borderline', 'rejected_negated', 'rejected_overlap', 'rejected_context',
            'example_id', 'example_phrase', 'example_decision', 'example_text', 'example_source', 'self_test', 'borderline_example_id', 'borderline_example']
    write_csv(os.path.join(out_dir, 'rules_with_examples.csv'), rule_rows, flds)
    write_csv(os.path.join(out_dir, 'vocab_terms_observed.csv'), B['terms'], ['category', 'rule', 'decision', 'phrase', 'records', 'example_id', 'example'])
    write_csv(os.path.join(out_dir, 'vocab_misspellings.csv'), B['misspell'], ['canonical', 'variant', 'records', 'example_id', 'example'])
    write_csv(os.path.join(out_dir, 'vocab_shorthand.csv'), B['short'], ['token', 'meaning', 'how_known', 'records', 'example_id', 'example'])
    write_csv(os.path.join(out_dir, 'vocab_fused_words.csv'), B['fused'], ['fused_token', 'split', 'records', 'example_id', 'example'])
    write_csv(os.path.join(out_dir, 'vocab_informal.csv'), B['informal'], ['category', 'rule', 'decision', 'phrase', 'records', 'example_id', 'example'])
    lab_rows = [dict(label=l['label'], records=l['n'], pct_habitability=l['pct_hab'], pct_paperwork=l['pct_paper'], pct_other=l['pct_other'], pct_nothing_found=l['pct_none'],
                     top_categories='; '.join('%s %.0f%%' % (c, p) for c, p in l['top']), used_to_infer=l['inferred'], inferred_share_pct=l['inferred_share'],
                     example_id=(l['example']['id'] if l['example'] else ''), example=(l['example']['text'] if l['example'] else '')) for l in B['labels']]
    write_csv(os.path.join(out_dir, 'city_labels.csv'), lab_rows, list(lab_rows[0].keys()) if lab_rows else ['label'])
    write_csv(os.path.join(out_dir, 'manual_review_pocket.csv'), B['pocket'], ['record_id', 'category', 'label', 'rule', 'phrase', 'reason', 'district', 'year', 'author', 'text', 'suggested_decision', 'decision'])
    write_csv(os.path.join(out_dir, 'unmatched_statements.csv'), B['unmatched'], ['record_id', 'year', 'district', 'author', 'channel', 'city_labels', 'text'])
    cmp = B['cmp_rows']
    if cmp:
        write_csv(os.path.join(out_dir, 'old_vs_new_by_category.csv'), [dict(population=c['pop'], old_category=c['old_cat'], lane=c['lane'], new_targets=';'.join(c['new_targets']), records_in_population=c['n_pop'], old_flagged=c['n_old'],
                                                                         new_flagged=c['n_new'], both=c['both'], old_only=c['old_only'], new_only=c['new_only'], old_flags_that_are_only_TRAO_or_EDRA_label=c['label_only'],
                                                                         what_old_flagged_records_contain='; '.join('%s %d' % (a, b) for a, b in c['composition'])) for c in cmp],
                  ['population', 'old_category', 'lane', 'new_targets', 'records_in_population', 'old_flagged', 'new_flagged', 'both', 'old_only', 'new_only', 'old_flags_that_are_only_TRAO_or_EDRA_label', 'what_old_flagged_records_contain'])
        exr = []
        for c in cmp:
            if c['pop'] != 'all_complaints': continue
            for e in c['ex_old']: exr.append(dict(old_category=c['old_cat'], side='old flagged, new did not', record_id=e['id'], old_phrase=e['phrase'], new_categories=';'.join(e['new']), text=e['text']))
            for e in c['ex_new']: exr.append(dict(old_category=c['old_cat'], side='new flagged, old did not', record_id=e['id'], old_phrase='', new_categories=';'.join(e['new']), text=e['text']))
        write_csv(os.path.join(out_dir, 'old_vs_new_examples.csv'), exr, ['old_category', 'side', 'record_id', 'old_phrase', 'new_categories', 'text'])
        write_csv(os.path.join(out_dir, 'old_vs_new_all_disagreements.csv'), B['disag'], ['old_category', 'side', 'record_id', 'old_phrases', 'new_categories', 'new_borderline', 'district', 'year', 'authorship'])
    D = B['dist']
    prow = []
    for t in D['table']:
        for c in D['cats']: prow.append(dict(district=t['district'], category=c, label=CAT_LABEL.get(c, c), records_in_district=t['n'], pct_of_district_records=t['rates'][c], pct_year_standardised=t['std'][c], citywide_pct=D['city'][c]))
    write_csv(os.path.join(out_dir, 'district_profile.csv'), prow, ['district', 'category', 'label', 'records_in_district', 'pct_of_district_records', 'pct_year_standardised', 'citywide_pct'])
    pr = []
    for p in D['pairs']:
        for x in p['alike']: pr.append(dict(district_a=p['a'], district_b=p['b'], cosine=p['cosine'], mean_abs_diff_pp=p['mad_pp'], kind='alike', category=x['cat'], a_std_pct=x['a_std'], b_std_pct=x['b_std'], a_raw_pct=x['a_raw'], b_raw_pct=x['b_raw'], a_n=x['a_n'], b_n=x['b_n'], z=x['z']))
        for x in p['different']: pr.append(dict(district_a=p['a'], district_b=p['b'], cosine=p['cosine'], mean_abs_diff_pp=p['mad_pp'], kind='different', category=x['cat'], a_std_pct=x['a_std'], b_std_pct=x['b_std'], a_raw_pct=x['a_raw'], b_raw_pct=x['b_raw'], a_n=x['a_n'], b_n=x['b_n'], z=x['z']))
    write_csv(os.path.join(out_dir, 'district_pairs.csv'), pr, ['district_a', 'district_b', 'cosine', 'mean_abs_diff_pp', 'kind', 'category', 'a_std_pct', 'b_std_pct', 'a_raw_pct', 'b_raw_pct', 'a_n', 'b_n', 'z'])


# ====================================================================================================
# EXAMPLES - one exact example per rule, copied from the records (whitespace normalised). Regenerated by the build, checked at start-up.
# ====================================================================================================
EXAMPLES = {
    'APPL-01': {"id": '004170-04CP', "decision": 'ACCEPT', "phrase": 'DISHWASHER LEAKS', "text": 'DISHWASHER LEAKS UNDER KITCHEN FLOOR--TOLD LANDLORD IN JULY--ALSO WIRING PROBLEMS WOTH GAS FIREPLACE'},
    'APPL-02': {"id": '014038-25CP', "decision": 'ACCEPT', "phrase": 'delayed and refused fridge', "text": 'Landlord delayed and refused fridge maintenance over the course of 72+ hours. I have ordered a small fridge would like to deduct from my rent'},
    'CONSTR-01': {"id": '003711-22CP', "decision": 'ACCEPT', "phrase": 'no permit', "text": 'grading in a known ECA excavator steep slope, no permit for foundation, doing work outside of plans'},
    'CONSTR-02': {"id": '009249-23CP', "decision": 'ACCEPT', "phrase": 'construction', "text": 'tenant rights - repairs/question re: construction taking place, wants to see if they apply for TRAO'},
    'CTX-01': {"id": '004526-07CP', "decision": 'ACCEPT', "phrase": 'SHA', "text": 'Shed is leaning toward the parking area of the SHA property located adj north at 2851 SW Dakota St.'},
    'DEP-01': {"id": '008926-22CP', "decision": 'ACCEPT', "phrase": 'deposit', "text": "I'm disputing a $100 cleaning fee deducted from my deposit. I left the place clean when I moved out."},
    'DEP-02': {"id": '008041-19CP', "decision": 'ACCEPT', "phrase": 'non-refundable', "text": 'POTA--per phone call--can you charge for removing tenants from lease? Questions about non-refundable fees'},
    'DEP-03': {"id": '010063-22CP', "decision": 'BORDERLINE', "phrase": 'refund', "text": "Per Online; It's been 3 months andI have not received the refund for rent and a credit on myledger."},
    'DOOR-01': {"id": '006267-20CP', "decision": 'ACCEPT', "phrase": 'door broken', "text": 'Intercom at front door broken. No ability to give access to visitors, deliveries, service, essential'},
    'DOOR-02': {"id": '009365-18CP', "decision": 'BORDERLINE', "phrase": 'squatters', "text": 'PM unresponsive to maintenance requests, security concerns, squatters w/dog in pet-free building'},
    'DOOR-03': {"id": '006267-20CP', "decision": 'ACCEPT', "phrase": 'Intercom at front door broken', "text": 'Intercom at front door broken. No ability to give access to visitors, deliveries, service, essential'},
    'DOOR-04': {"id": '008475-24CP', "decision": 'ACCEPT', "phrase": 'unable to receive mail', "text": 'Mailboxes were broken into and landlord has not yet fixed. Tenants are unable to receive mail for a month'},
    'DOOR-05': {"id": '003435-23CP', "decision": 'ACCEPT', "phrase": 'window issues/cracked', "text": 'mold, floor tearing, window issues/cracked, toliet seatbroken, cabinets broken, call box isnt working'},
    'DOOR-06': {"id": '005682-25CP', "decision": 'ACCEPT', "phrase": "latch, don't close", "text": "All windows in unit are not functioning properly. They don't latch, don't close. Mgmt. has not fixed."},
    'DOOR-07': {"id": '004507-18CP', "decision": 'ACCEPT', "phrase": 'no thumb latch', "text": 'HOUSING - Door locks are key only, no thumb latch on deadbolt inside'},
    'ELEC-01': {"id": '001191-15CP', "decision": 'ACCEPT', "phrase": 'NO ELETRICITY', "text": 'NO ELETRICITY - Tenant has a case manager helping him. You will need to ask for Jeremy when you call.'},
    'ELEC-02': {"id": '003495-08CP', "decision": 'ACCEPT', "phrase": 'EXPOSED WIRING', "text": 'SEVERAL ELECTRICAL OUTLETS DO NOT WORK AND ONE HAS EXPOSED WIRING--PLUMBING LEAKS BELOW KITCHEN SINK'},
    'ELEC-03': {"id": '003495-08CP', "decision": 'ACCEPT', "phrase": 'OUTLETS DO NOT WORK', "text": 'SEVERAL ELECTRICAL OUTLETS DO NOT WORK AND ONE HAS EXPOSED WIRING--PLUMBING LEAKS BELOW KITCHEN SINK'},
    'ELEC-04': {"id": '004540-23CP', "decision": 'ACCEPT', "phrase": 'electrical problems', "text": 'Severe electrical problems in my unit. Smart lights and thermostat have wreaked havoc in my apartment.'},
    'ELEC-05': {"id": '001494-07CP', "decision": 'ACCEPT', "phrase": 'lights blow out', "text": 'Black mold in bathroom and insufficient electrical capacity in unit--lights blow out too frequently.'},
    'ELEC-06': {"id": '003157-05CP', "decision": 'ACCEPT', "phrase": 'NO LIGHTS', "text": 'NO LIGHTS SINCE JUNE 21ST. THERE IS ALSO MOLD IN THE WALLS AND ON THE WINDOWS OF THE BUILDING.'},
    'ELEC-07': {"id": '015252-25CP', "decision": 'ACCEPT', "phrase": 'breaker box inside', "text": 'Landlord turns power off at breaker box inside of the home'},
    'ELEV-01': {"id": '000218-24CP', "decision": 'ACCEPT', "phrase": 'elevator has been out', "text": 'Building has been non-ADA compliant. The public elevator has been out of service for nearly a month.'},
    'ELEV-02': {"id": '010475-23CP', "decision": 'ACCEPT', "phrase": 'ADA violation', "text": 'The only elevator available in the building has been broken for about 6 days. This an ADA violation.'},
    'ELEV-03': {"id": '001307-20CP', "decision": 'ACCEPT', "phrase": 'inconsistent service from the elevator', "text": 'lack of maintenance and inconsistent service from the elevator in Building A'},
    'ELEV-04': {"id": '009902-25CP', "decision": 'ACCEPT', "phrase": 'elevator … not operational', "text": 'We have a single elevator in this apartment building and it has been not operational since June 30.'},
    'ENTRY-01': {"id": '004801-09CP', "decision": 'ACCEPT', "phrase": 'ENTERED WITHOUT', "text": 'THE LOCK ON THE FRONT DOOR TO BUILDING #21C HAS BEEN BROKEN SO THAT IT CAN BE ENTERED WITHOUT A KEY'},
    'ENTRY-02': {"id": '002172-24CP', "decision": 'ACCEPT', "phrase": 'landlord entry', "text": "tenant rights - landlord entry 2/27 - 2/29 I don't want them to come in they are taking me to court"},
    'ENTRY-03': {"id": '010232-23CP', "decision": 'BORDERLINE', "phrase": 'privacy', "text": 'Tenant would like to know rights regarding Maintenance requests/issues and also tenants privacy rights etc.'},
    'ENTRY-04': {"id": '014202-25CP', "decision": 'ACCEPT', "phrase": 'notices to enter', "text": 'notices to enter posted on door related to 014201-25CP, wants to know rents rights'},
    'EVICT-01': {"id": '004862-24CP', "decision": 'ACCEPT', "phrase": '10 DAY NOTICE TO COMPLY', "text": 'EVICTION - DOG THERE ARE OTHER DOGS AND THEY ARE NOT ALLOWING MINE 10 DAY NOTICE TO COMPLY OR VACATE'},
    'EVICT-02': {"id": '000531-20CP', "decision": 'ACCEPT', "phrase": 'eviction', "text": 'Apartment is damaged from flooding, rent increase eff 12/1/19, landlord threatening eviction notice.'},
    'EVICT-03': {"id": '001693-22CP', "decision": 'ACCEPT', "phrase": 'kicked me out', "text": 'tenant rights - landlord just kicked me out of where I live did not give any notice just put me out'},
    'EVICT-04': {"id": '000794-24CP', "decision": 'ACCEPT', "phrase": 'terminate lease', "text": 'tenant rights - pipe burst/had to move out want to terminate lease need guidance what are my options'},
    'EVICT-05': {"id": '011665-19CP', "decision": 'ACCEPT', "phrase": 'notice for a sale', "text": 'On a month to month lease for a condo. Owner would like to know how to give proper notice for a sale'},
    'EVICT-06': {"id": '007194-25CP', "decision": 'ACCEPT', "phrase": 'son wants to move in', "text": 'Landlord issued 90 day vacate notice because son wants to move in to unit, tenant wondering her rights'},
    'EVICT-07': {"id": '002933-25CP', "decision": 'ACCEPT', "phrase": 'he wants to move in', "text": 'Eviction - landlord claiming he wants to move in, tenant is doubting that'},
    'EVICT-08': {"id": '005926-18CP', "decision": 'ACCEPT', "phrase": 'mutual termination', "text": 'Tenant said mold in unit making tenants sick. discussed mutual termination & schedule inspection'},
    'EVICT-09': {"id": '004623-24CP', "decision": 'BORDERLINE', "phrase": 'selling house', "text": 'Owner is selling house. tenant was given a notice to move out by 6/30. Is this legal, what are rights?'},
    'EVICT-10': {"id": '014230-25CP', "decision": 'ACCEPT', "phrase": 'renovations tenant was given a 20day notice', "text": 'Doing renovations tenant was given a 20day notice. Is this legal, need more time than 20days. What are rights?'},
    'FIRE-01': {"id": '003548-13CP', "decision": 'ACCEPT', "phrase": 'No smoke detector', "text": 'No smoke detector. No hot water. Black mold, particularly around window seal. Cracks in bathroom wall.'},
    'FIRE-02': {"id": '013375-25CP', "decision": 'ACCEPT', "phrase": 'carbon monoxide', "text": "Aging furnace with safety concerns, have not updated it, haven't installed all carbon monoxide detectors."},
    'FIRE-03': {"id": '003114-22CP', "decision": 'ACCEPT', "phrase": 'Gas leak', "text": 'Gas leak, inhaled toxic fumes. Management has not offered any compensation or concessions for residents.'},
    'FIRE-04': {"id": '008119-20CP', "decision": 'ACCEPT', "phrase": 'Fire hazard', "text": 'Fire hazard. Regularly leaving trash chute walled off with garbage. Has become a weekly occurence.'},
    'FIRE-05': {"id": '005984-15CP', "decision": 'ACCEPT', "phrase": 'due to fire', "text": 'Building vacated due to fire in unit #6. No electricity, heat, security and 2nd means of egress removed.'},
    'FIRE-06': {"id": '003736-14CP', "decision": 'ACCEPT', "phrase": 'No … exit', "text": 'Circuits blow frequently. Electrical box is locked. No windows in bedroom with only one exit. Rats.'},
    'FIRE-07': {"id": '006526-24CP', "decision": 'ACCEPT', "phrase": 'fire alarm sensor in lobby area is faulty', "text": 'fire alarm sensor in lobby area is faulty needs to be reset have reported to mgmt not addressing the issue'},
    'FIRE-08': {"id": '007471-17CP', "decision": 'BORDERLINE', "phrase": 'smells like burnt', "text": 'Inoperable electrical outlet in kitchen - smells like burnt electrical. Stain on plastic casing has turned black. Landlord unresponsive to requests.***See attached photo***'},
    'FIRE-09': {"id": '008223-23CP', "decision": 'ACCEPT', "phrase": 'recent fire', "text": 'recent fire, water damage need to vacate ASAP landlord not accommodating me for this inconvenience need help!'},
    'FIRE-10': {"id": '012925-23CP', "decision": 'ACCEPT', "phrase": 'alarm … not installed', "text": "Sprinklers, fire alarm system, and proper exits not installed in enclosed hallway between properties of 2122 and 2118. This hallway connects the 2 properties so food can be cooked in 2122 and brought to 2118. The exit door to the alleyway is not marked as an Exit and doors going to water closets or other storage areas not labeled properly to prevent people from thinking it's an exit. Both spaces leased by same tenant. Tenant tied into water and sewer pipes but don't see a permit for that wo"},
    'HABU-01': {"id": '003750-23CP', "decision": 'ACCEPT', "phrase": 'maintenance issues', "text": 'HBMC violations: damaged ceiling, holes observed along stairwell, maintenance issues with door, etc.'},
    'HABU-02': {"id": '004610-06CP', "decision": 'ACCEPT', "phrase": 'FAILED TO REPAIR', "text": 'THERE IS A LEAK IN BATHROOM CEILING THAT LANDLORD HAS FAILED TO REPAIR--A MOLD PROBLEM IS DEVELOPING'},
    'HABU-03': {"id": '004271-12CP', "decision": 'ACCEPT', "phrase": 'lack of maintenance', "text": 'Boarding house, water does not get up to temperture, leaks, general lack of maintenance, Sisley property.'},
    'HAZ-01': {"id": '001079-23CP', "decision": 'ACCEPT', "phrase": 'fumes', "text": 'fumes and smell in apartment is really acidic, i get light headed and maintenance will not address.'},
    'HAZ-02': {"id": '006258-24CP', "decision": 'ACCEPT', "phrase": 'no fresh air', "text": 'There has been no fresh air ventilation in the corridors & laundry rooms, since end of January 2024.'},
    'HAZ-03': {"id": '005179-21CP', "decision": 'ACCEPT', "phrase": 'Cigarette smoke', "text": 'Smokers in the courtyard. Cigarette smoke is effecting multiple units and neighboring buildings.'},
    'HEAT-01': {"id": '001553-11CP', "decision": 'ACCEPT', "phrase": 'NO HEAT', "text": 'BUILDING HAS HAD NO HEAT SINCE NOVEMBER--MANAGEMENT HAS MANY EXCUSES BUT NOW TENANTS ARE REALLY COLD'},
    'HEAT-02': {"id": '003311-14CP', "decision": 'ACCEPT', "phrase": 'Insufficient heat', "text": 'Insufficient heat for running water and very low water pressure for this newly built building.'},
    'HEAT-03': {"id": '001135-16CP', "decision": 'ACCEPT', "phrase": 'Heat in bedroom and bathroom not working', "text": '1)Hole in ceiling leaking.2)Leaking water around house. 3) Heat in bedroom and bathroom not working.'},
    'HEAT-04': {"id": '014228-24CP', "decision": 'ACCEPT', "phrase": 'very cold in my apartment', "text": 'Refusing to fix a broken window for over 2 weeks. It is very cold in my apartment because of this.'},
    'HEAT-05': {"id": '001032-04CP', "decision": 'ACCEPT', "phrase": 'HEAT … 65 DEGREES', "text": 'HEAT IS TURNED ON AT 4AM--IS TURNED OFF AT 8PM--APT GETS COLDER THAN 65 DEGREES BEFORE 10:30PM'},
    'HVAC-01': {"id": '010987-23CP', "decision": 'ACCEPT', "phrase": 'Air conditioning has been broken', "text": 'Air conditioning has been broken for 2months. Management has not addressed. AmI owed any compensation?'},
    'HW-01': {"id": '010576-21CP', "decision": 'ACCEPT', "phrase": 'NO HOT WATER', "text": 'NO HOT WATER. AMONTH OR SO OF FUTZINGWITH ISSUE AND NOW PMIS SAYING NOT GOING TOLOOK INTO IT FURTHER'},
    'HW-02': {"id": '009351-21CP', "decision": 'ACCEPT', "phrase": 'poor or little hot water', "text": 'There is no boiler- and as a result, has been no heat since September, and poor or little hot water.'},
    'HW-03': {"id": '002769-12CP', "decision": 'ACCEPT', "phrase": 'Water only gets to lukewarm', "text": 'Water only gets to lukewarm after running for 10 mins., this has been a longstanding problem.'},
    'HW-04': {"id": '004249-18CP', "decision": 'ACCEPT', "phrase": 'scalding', "text": 'HOUSING - The restroom sink faucet is scalding hot. Enough to blister skin. The restroom is not ada complaint.'},
    'INFORMAL-01': {"id": '001922-24CP', "decision": 'ACCEPT', "phrase": 'shit hole', "text": 'Bruce is even worse than the dumb cunt before him. Seattle is a fucking piece of garbage shit hole.'},
    'INQ-01': {"id": '000711-19CP', "decision": 'ACCEPT', "phrase": 'Would like to know', "text": 'Are owners allowed to create a short lease for change of use? Would like to know rights as a tenant.'},
    'INQ-02': {"id": '011537-19CP', "decision": 'ACCEPT', "phrase": 'can I break', "text": 'How can I break my lease? I live above the garbage collection area, and the smells are unbearable.'},
    'INSULT-01': {"id": '001922-24CP', "decision": 'ACCEPT', "phrase": 'fucking', "text": 'Bruce is even worse than the dumb cunt before him. Seattle is a fucking piece of garbage shit hole.'},
    'INSULT-02': {"id": '005603-23CP', "decision": 'ACCEPT', "phrase": 'corrupt', "text": "Building be busted. Slum lords don't do shit. Paid off corrupt city hall libtards don't do shit."},
    'LEAK-01': {"id": '000531-20CP', "decision": 'ACCEPT', "phrase": 'flooding', "text": 'Apartment is damaged from flooding, rent increase eff 12/1/19, landlord threatening eviction notice.'},
    'LEAK-02': {"id": '001035-09CP', "decision": 'ACCEPT', "phrase": 'roof leak', "text": 'Corner leaks (believe it is from roof leak) and is causing mold. Elevator has not worked for a year.'},
    'LEAK-03': {"id": '001007-05CP', "decision": 'ACCEPT', "phrase": 'LEAKING', "text": 'BATHTUB IN UNIT #315 HAS BEEN LEAKING FOR A MONTH--IS DRIPPING INTO UNIT #215--MANAGER HAS BEEN TOLD'},
    'LEAK-04': {"id": '001789-14CP', "decision": 'ACCEPT', "phrase": 'when it rains, toilet leaks', "text": 'Ceiling leaks from walls when it rains, toilet leaks and the landlord is not willing to make repairs.'},
    'LEAK-05': {"id": '002673-13CP', "decision": 'ACCEPT', "phrase": 'Drafts', "text": 'Backed up plumbing. Sink leak in bathroom causing mold underneath sink. Drafts. Ongoing for a month.'},
    'LEASE-01': {"id": '000958-19CP', "decision": 'ACCEPT', "phrase": 'month to month', "text": 'Owner wants to sell property, tenant is on month to month lease. How do they do an eviction legally?'},
    'LEASE-02': {"id": '006153-25CP', "decision": 'ACCEPT', "phrase": 'Lease up', "text": 'Lease up at end of month, no renewal letter received, landlord gave verbal notice for rent increase.'},
    'LEASE-03': {"id": '000883-20CP', "decision": 'ACCEPT', "phrase": 'term lease', "text": 'Owner changing the month to month lease to a term lease. What are my rights?'},
    'LOCK-01': {"id": '008722-21CP', "decision": 'ACCEPT', "phrase": 'LOCKOUT', "text": "LOCKOUT INQUIRY. TENANT DECEASED. PARTNER/FAMILY DENIED ACCESS TO UNIT TO RECOVER DECEASED'S PROPERTY."},
    'MOD-01': {"id": '001194-05CP', "decision": 'ACCEPT', "phrase": 'NO RESPONSE', "text": 'REFRIDGERATOR HAS BEEN BROKEN (NOT RUNNING) FOR ONE WEEK--LANDLORD HAS BEEN NOTIFIED BUT NO RESPONSE'},
    'MOD-02': {"id": '002646-24CP', "decision": 'ACCEPT', "phrase": 'asthma', "text": 'Tenant moved in about a month ago, and has had bad asthma due to mold. Tenant would like unit tested.'},
    'MOD-03': {"id": '002971-11CP', "decision": 'ACCEPT', "phrase": 'CHILDREN', "text": "BLACK MOLD IN THE SHOWER--LANDLORD (SHA) WON'T HELP HER TO GET RID OF IT--MAKING HER CHILDREN SICK"},
    'MOLD-01': {"id": '001035-09CP', "decision": 'ACCEPT', "phrase": 'mold', "text": 'Corner leaks (believe it is from roof leak) and is causing mold. Elevator has not worked for a year.'},
    'MOLD-02': {"id": '006036-14CP', "decision": 'ACCEPT', "phrase": 'condensation', "text": "Visible mold. The windows are always dripping with condensation and the landlord isn't doing anything."},
    'NEIGH-01': {"id": '006214-25CP', "decision": 'ACCEPT', "phrase": 'assaulting', "text": '3 tenants in home, one roommate is verbally assaulting another roommate, can this tenant be evicted?'},
    'NEIGH-02': {"id": '008050-22CP', "decision": 'ACCEPT', "phrase": 'fentanyl', "text": 'Per Online; Excessive smoke from fentanyl. Smells up the hallways, rooms, and common areas.'},
    'NOISE-01': {"id": '003206-25CP', "decision": 'ACCEPT', "phrase": 'noisy', "text": 'Management will not address a noisy neighbor,making noise all hours of the night. What are my rights?'},
    'NOISE-02': {"id": '012243-25CP', "decision": 'ACCEPT', "phrase": 'subwoofer', "text": 'Excessive noise. Music so loud on subwoofer it makes my apartment walls vibrate and shake'},
    'NOTICE-01': {"id": '003775-23CP', "decision": 'ACCEPT', "phrase": '180 days notice', "text": "I received a rent increase notice in February, effective May 1st. Isn't the new law 180 days notice?"},
    'OCC-01': {"id": '013655-24CP', "decision": 'ACCEPT', "phrase": 'too many people', "text": 'Eviction given, tenant also believes there are too many people living here for the allowed square footage, wondering his rights.'},
    'PEST-01': {"id": '001320-19CP', "decision": 'ACCEPT', "phrase": 'mice', "text": 'Has needed a new toilet since May 2018. Leaking kitchen and bathroom faucets. Also mice and roaches.'},
    'PEST-02': {"id": '003275-19CP', "decision": 'ACCEPT', "phrase": 'infestation', "text": 'Trying to charge the tenants fee for spraying for bed bug infestation from another member apartment.'},
    'PEST-03': {"id": '002708-19CP', "decision": 'ACCEPT', "phrase": 'bitten, and bringing fleas', "text": 'Flea infestation in the hallway of my bldg. I keep getting bitten, and bringing fleas into my unit.'},
    'PEST-04': {"id": '003924-05CP', "decision": 'ACCEPT', "phrase": 'beetles', "text": 'infestation of carpet beetles for about 6 months. Owner is aware and has not come out to fix problem.'},
    'PLUMB-01': {"id": '002019-14CP', "decision": 'ACCEPT', "phrase": 'raw sewage', "text": 'No plumbing in lower level bathroom, raw sewage backup in toilet. Deck also rotted and is dangerous.'},
    'PLUMB-02': {"id": '002019-14CP', "decision": 'ACCEPT', "phrase": 'backup', "text": 'No plumbing in lower level bathroom, raw sewage backup in toilet. Deck also rotted and is dangerous.'},
    'PLUMB-03': {"id": '000794-24CP', "decision": 'ACCEPT', "phrase": 'pipe burst', "text": 'tenant rights - pipe burst/had to move out want to terminate lease need guidance what are my options'},
    'PLUMB-04': {"id": '001007-05CP', "decision": 'ACCEPT', "phrase": 'BATHTUB IN UNIT #315 HAS BEEN LEAKING', "text": 'BATHTUB IN UNIT #315 HAS BEEN LEAKING FOR A MONTH--IS DRIPPING INTO UNIT #215--MANAGER HAS BEEN TOLD'},
    'PLUMB-05': {"id": '005165-24CP', "decision": 'ACCEPT', "phrase": 'sewage overflow', "text": 'Electrical and plumbing issues, sewage overflow, threatening tenant, rats living on premises.'},
    'PUB-01': {"id": '001719-20CP', "decision": 'ACCEPT', "phrase": 'Weeds', "text": 'Hazardous Weeds--per CSB--Blocking sidewalk or stairway. This makes the sidewalk not ADA accessible'},
    'PUB-02': {"id": '001719-20CP', "decision": 'ACCEPT', "phrase": 'Blocking sidewalk', "text": 'Hazardous Weeds--per CSB--Blocking sidewalk or stairway. This makes the sidewalk not ADA accessible'},
    'PUB-03': {"id": '006164-22CP', "decision": 'ACCEPT', "phrase": 'dumping on the streets', "text": 'There has been a large amount of illegal dumping on the streets and sidewalks outside of this property.'},
    'PUB-04': {"id": '006758-22CP', "decision": 'ACCEPT', "phrase": 'hedges', "text": 'Overgrown large hedges in alley between 21st & 22nd Ave - making driving and sight lines difficult'},
    'REG-01': {"id": '006066-21CP', "decision": 'ACCEPT', "phrase": 'rental registration', "text": 'Units 1, 102, 204, and 302 are rental properties operating without a rental registration license.'},
    'REG-02': {"id": '003561-25CP', "decision": 'ACCEPT', "phrase": 'RRIO inspected', "text": 'RRIO inspected my unit 25 days ago, and my landlord refused to complete the required maintenance service.'},
    'RELO-01': {"id": '001414-24CP', "decision": 'ACCEPT', "phrase": 'relocation', "text": "No water, ceiling collapsed, wants to know rights as tenant. Landlord won't assist with relocation."},
    'RELO-02': {"id": '010580-20CP', "decision": 'ACCEPT', "phrase": 'tenant … renovations', "text": 'inquire tenant rights, landlord started renovations to property did not inform me this was happening'},
    'RENT-01': {"id": '000531-20CP', "decision": 'ACCEPT', "phrase": 'rent increase', "text": 'Apartment is damaged from flooding, rent increase eff 12/1/19, landlord threatening eviction notice.'},
    'RENT-02': {"id": '008926-22CP', "decision": 'ACCEPT', "phrase": '$100 cleaning fee', "text": "I'm disputing a $100 cleaning fee deducted from my deposit. I left the place clean when I moved out."},
    'RENT-03': {"id": '012867-25CP', "decision": 'ACCEPT', "phrase": 'rent assistance', "text": 'Wants to know rights as a tenant - sent a costly utility bill, would like referral to rent assistance'},
    'RENT-04': {"id": '003275-19CP', "decision": 'BORDERLINE', "phrase": 'fee', "text": 'Trying to charge the tenants fee for spraying for bed bug infestation from another member apartment.'},
    'RENT-05': {"id": '001313-24CP', "decision": 'ACCEPT', "phrase": 'screening fee', "text": 'Was looking to see if lease is illegal and if you can get your screening fee back.'},
    'RENT-06': {"id": '012992-24CP', "decision": 'ACCEPT', "phrase": 'refusing to take rental', "text": 'landlord refusing to take rental pymt stating I need to pay a cable bill that I did not agree to extended contract/canceled after introductory offer'},
    'RENT-07': {"id": '011695-19CP', "decision": 'ACCEPT', "phrase": 'New fees', "text": 'New fees; building charging pet registration fee and now have to pay for trash collecting at door ($25)'},
    'RET-01': {"id": '000531-20CP', "decision": 'ACCEPT', "phrase": 'landlord threatening', "text": 'Apartment is damaged from flooding, rent increase eff 12/1/19, landlord threatening eviction notice.'},
    'RET-02': {"id": '003146-21CP', "decision": 'ACCEPT', "phrase": 'discriminated', "text": 'tenant rights/rent increase late fees I have a disability and feel like I am being discriminated against'},
    'RET-03': {"id": '001125-22CP', "decision": 'ACCEPT', "phrase": 'HARASSMENT', "text": 'LANDLORD GUIDANCEJCEO GUIDANCE, LOCKSCHANGED BY TENANT.TENANT HAS ALSO FILEDHARASSMENT AND STALKINGRESTRAINING ORDER.'},
    'RET-04': {"id": '000202-19CP', "decision": 'BORDERLINE', "phrase": 'after tenant complained', "text": "Installed a dishwasher, didn't install correctly. Water leaks and doesn't fill up with water as it should. Mgmt entered home without permission after tenant complained itwasn't installed correctly."},
    'ROLE-01': {"id": '010794-25CP', "decision": 'ACCEPT', "phrase": 'Landlord has questions', "text": 'Landlord has questions about rule changes, renewals, right of first refusal, termination of tenancy.'},
    'ROLE-02': {"id": '007583-20CP', "decision": 'ACCEPT', "phrase": 'landlord rights', "text": 'landlord rights, just cause evictions, tenant has changed the locks what can I do about this'},
    'SAN-01': {"id": '002228-23CP', "decision": 'ACCEPT', "phrase": 'GARBAGE PILED', "text": 'GARBAGE PILED UPIN GARAGE; SEVERALBAGS DUE TO OVERFLOWOF CONTAINERS. NO PICK UPFOR TWO WEEKS OR MORE'},
    'SAN-02': {"id": '006721-22CP', "decision": 'ACCEPT', "phrase": 'urine', "text": 'black mold throughout the building. Landlord will not clean. The entire building smells like urine.'},
    'SAN-03': {"id": '006605-23CP', "decision": 'ACCEPT', "phrase": 'stinks', "text": "Junk in front and back of house. Fence was recently torn out and so it's visible to all. It stinks."},
    'SAN-04': {"id": '001079-23CP', "decision": 'BORDERLINE', "phrase": 'smell', "text": 'fumes and smell in apartment is really acidic, i get light headed and maintenance will not address.'},
    'SEV-01': {"id": '002957-18CP', "decision": 'ACCEPT', "phrase": 'UNFIT', "text": 'UNFIT-Hole in the roof/north side. Chimney bricks falling off. Vacant case 1038404, 1039258, 1038883'},
    'SEV-02': {"id": '010141-25CP', "decision": 'ACCEPT', "phrase": 'Forced to leave property due to', "text": 'Forced to leave property due to uninhabitability, tenant wondering her rights. Related to 008685-25CP'},
    'STRUCT-01': {"id": '001045-08CP', "decision": 'ACCEPT', "phrase": 'sagging', "text": 'In the basement of this 2 story apartment building the ceiling / beams have shifted and are sagging.'},
    'STRUCT-02': {"id": '002957-18CP', "decision": 'ACCEPT', "phrase": 'Hole in the roof', "text": 'UNFIT-Hole in the roof/north side. Chimney bricks falling off. Vacant case 1038404, 1039258, 1038883'},
    'STRUCT-03': {"id": '001045-08CP', "decision": 'ACCEPT', "phrase": 'beams have shifted and are sagging', "text": 'In the basement of this 2 story apartment building the ceiling / beams have shifted and are sagging.'},
    'STRUCT-04': {"id": '004259-16CP', "decision": 'ACCEPT', "phrase": 'ceiling has cracks', "text": 'leak in the bathroom, ceiling has cracks and black mold; leak also comes through the bedroom ceiling'},
    'STRUCT-05': {"id": '003752-18CP', "decision": 'ACCEPT', "phrase": 'Ceiling height', "text": "Possible HBMC violations. Ceiling height is less than 6' in height - in kitchen, bedroom, and bathroom."},
    'UBILL-01': {"id": '009727-20CP', "decision": 'ACCEPT', "phrase": 'water bill', "text": 'need to know tenant rights - unable to pay water bill, landlord is threating to evict if I cannot pay'},
    'UTIL-01': {"id": '005911-07CP', "decision": 'ACCEPT', "phrase": 'WATER AND HEAT WERE TURNED OFF', "text": 'FLOOD DAMAGE TO CARPET/FLOORS--WATER AND HEAT WERE TURNED OFF YESTERDAY DUE TO NON PAYMENT'},
    'UTIL-02': {"id": '002677-14CP', "decision": 'ACCEPT', "phrase": 'Electricity was shut off', "text": 'Electricity was shut off on 5/13/14 due to non-payment. Tenant has also received notice of water shut off.'},
    'UTIL-03': {"id": '001830-10CP', "decision": 'ACCEPT', "phrase": 'Gas turned off', "text": 'Gas turned off yesterday (radiator heat in building). No heat and no hot water in building.'},
    'UTIL-04': {"id": '004910-05CP', "decision": 'ACCEPT', "phrase": 'TURNED OFF WATER', "text": 'OWNER TURNED OFF WATER 5 DAYS AGO/ TOOK OUT TOILET/ AND IS MAKING ADDITION TO BASEMENT W/O PERMITS.'},
    'UTIL-05': {"id": '012706-24CP', "decision": 'ACCEPT', "phrase": 'turned off power', "text": 'Landlord turned off power to my appliances on power switchboard to punish me when my rent was late'},
    'UTIL-06': {"id": '008177-17CP', "decision": 'ACCEPT', "phrase": 'shut off heat', "text": 'Per phone call: Landlord has shut off heat, refuses to maintain habitable temperature. Ongoing since 10/2017.'},
    'WATER-01': {"id": '000638-24CP', "decision": 'ACCEPT', "phrase": 'water shut off', "text": 'Building-wide water shut off due to pipe burst, intermittent hot water since beginning of the year.'},
    'WATER-02': {"id": '004159-08CP', "decision": 'ACCEPT', "phrase": 'LOW WATER PRESSURE', "text": 'VERY LOW WATER PRESSURE--HEAT WILL NOT TURN OFF--HEAT IS ON AT ALL TIMES, EVEN DURING SUMMER MONTHS'},
    'WATER-03': {"id": '015296-25CP', "decision": 'ACCEPT', "phrase": 'brown water', "text": 'Water appears to be leaking on ceiling, brown water area. Common area concerns. Roof has issues too.'},
    'WATER-04': {"id": '004322-05CP', "decision": 'ACCEPT', "phrase": 'WATER WILL BE SHUT OFF', "text": 'POWER HAS BEEN SHUT OFF TODAY FOR ENTIRE BUILDING--NOTICE HAS BEEN SENT TO TENANTS THAT WATER WILL BE SHUT OFF'},
    'ZONE-01': {"id": '005912-23CP', "decision": 'ACCEPT', "phrase": 'ZONING', "text": "POTA - break lease ZONING - basement apt not legal separate dwelling does not have it's own utilities"},
}

HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Complaint Vocabulary Audit</title>
<style>
:root{
  --bg:#f6f7f9;--fg:#1c2330;--muted:#5d6878;--card:#ffffff;--line:#dde2ea;--soft:#eef1f6;
  --hab:#0f766e;--hab-bg:#d9f1ee;--paper:#4338ca;--paper-bg:#e4e3fb;--other:#475569;--other-bg:#e5e9ef;--flag:#b45309;--flag-bg:#fdecc8;
  --ok:#15803d;--bad:#b91c1c;--mark:#fff1a8;--accent:#1d4ed8;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#10141b;--fg:#e6eaf0;--muted:#9aa5b5;--card:#171d27;--line:#2a3340;--soft:#1e2631;
    --hab:#5eead4;--hab-bg:#12373a;--paper:#a5b4fc;--paper-bg:#24274f;--other:#cbd5e1;--other-bg:#2a3340;--flag:#fbbf24;--flag-bg:#3a2f12;
    --ok:#4ade80;--bad:#f87171;--mark:#5b4b00;--accent:#7aa2ff;
  }
}
:root[data-theme="dark"]{
  --bg:#10141b;--fg:#e6eaf0;--muted:#9aa5b5;--card:#171d27;--line:#2a3340;--soft:#1e2631;
  --hab:#5eead4;--hab-bg:#12373a;--paper:#a5b4fc;--paper-bg:#24274f;--other:#cbd5e1;--other-bg:#2a3340;--flag:#fbbf24;--flag-bg:#3a2f12;
  --ok:#4ade80;--bad:#f87171;--mark:#5b4b00;--accent:#7aa2ff;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
header.top{background:var(--card);border-bottom:1px solid var(--line);padding:22px 0 14px}
header.top h1{margin:0 0 4px;font-size:1.6rem;line-height:1.2}
header.top p{margin:2px 0;color:var(--muted);font-size:.95rem}
nav.toc{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);overflow-x:auto;white-space:nowrap}
nav.toc a{display:inline-block;padding:9px 10px;font-size:.88rem;text-decoration:none;color:var(--muted)}
nav.toc a:hover{color:var(--fg)}
section{margin:28px 0}
section>h2{font-size:1.3rem;margin:0 0 4px}
section>.sub{color:var(--muted);margin:0 0 12px;font-size:.95rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat .n{font-size:1.65rem;font-weight:700;line-height:1.1}
.stat .l{color:var(--muted);font-size:.85rem;margin-top:3px}
.stat.hab{border-left:5px solid var(--hab)} .stat.paper{border-left:5px solid var(--paper)} .stat.flag{border-left:5px solid var(--flag)} .stat.other{border-left:5px solid var(--other)}
table{width:100%;border-collapse:collapse;font-size:.9rem;background:var(--card)}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:600;position:sticky;top:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.tw table{min-width:640px}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.75rem;font-weight:600;white-space:nowrap}
.chip.HAB{background:var(--hab-bg);color:var(--hab)} .chip.PAPER{background:var(--paper-bg);color:var(--paper)} .chip.OTHER{background:var(--other-bg);color:var(--other)} .chip.FLAG{background:var(--flag-bg);color:var(--flag)}
.chip.ok{background:var(--hab-bg);color:var(--ok)} .chip.bad{background:var(--flag-bg);color:var(--bad)}
.bar{background:var(--soft);border-radius:4px;height:9px;min-width:70px;position:relative}
.bar>span{display:block;height:100%;border-radius:4px;background:var(--accent)}
.bar.HAB>span{background:var(--hab)} .bar.PAPER>span{background:var(--paper)} .bar.OTHER>span{background:var(--other)} .bar.FLAG>span{background:var(--flag)}
.mut{color:var(--muted)} .small{font-size:.85rem}
mark{background:var(--mark);color:inherit;padding:0 2px;border-radius:3px}
.ex{font-size:.88rem}
.ex .id{color:var(--muted);font-size:.78rem}
details{margin:6px 0}
summary{cursor:pointer;color:var(--accent)}
code,.mono{font-family:ui-monospace,Consolas,Menlo,monospace;font-size:.78rem;word-break:break-all}
pre.pat{white-space:pre-wrap;word-break:break-all;background:var(--soft);padding:8px;border-radius:6px;margin:6px 0;font-size:.75rem}
input[type=search],select{padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);font:inherit;font-size:.9rem}
button{padding:7px 12px;border:1px solid var(--line);border-radius:6px;background:var(--soft);color:var(--fg);font:inherit;font-size:.9rem;cursor:pointer}
button.pri{background:var(--accent);color:#fff;border-color:var(--accent)}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
ul.find{margin:6px 0 6px 18px;padding:0} ul.find li{margin:5px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.matrix{border-collapse:separate;border-spacing:3px;width:auto;background:transparent}
.matrix th,.matrix td{border:0;text-align:center;padding:8px 10px;min-width:54px;border-radius:6px}
.matrix td{cursor:pointer;font-variant-numeric:tabular-nums;font-size:.85rem}
.matrix td.self{background:var(--soft);cursor:default;color:var(--muted)}
.note{border-left:4px solid var(--flag);background:var(--flag-bg);padding:8px 12px;border-radius:0 8px 8px 0;margin:10px 0;font-size:.9rem}
.tabs button{border-radius:6px 6px 0 0}
.tabs button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
footer{color:var(--muted);font-size:.85rem;padding:18px 0 40px}
@media (max-width:640px){header.top h1{font-size:1.3rem}.stat .n{font-size:1.4rem}}
@media print{nav.toc{display:none}}
</style>
</head>
<body>
<header class="top"><div class="wrap" id="hdr"></div></header>
<nav class="toc"><div class="wrap" id="toc"></div></nav>
<main class="wrap" id="app"></main>
<footer class="wrap" id="foot"></footer>
<script>
"use strict";
const DATA = /*__DATA__*/null;
const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = n => (n==null||n==='')?'':Number(n).toLocaleString('en-US');
const pc = (x, d=1) => (x==null||x==='')?'':Number(x).toFixed(d)+'%';
const CL = DATA.cat_label, AL = DATA.author_label;
const catName = c => CL[c] || c;
function hl(text, phrase){
  text = String(text||''); if(!phrase) return esc(text);
  const parts = String(phrase).split(' … ').map(p=>p.trim()).filter(Boolean);
  let out = esc(text);
  parts.forEach(p=>{
    const e = esc(p).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    try{ out = out.replace(new RegExp(e,'i'), m=>'<mark>'+m+'</mark>'); }catch(_){}
  });
  return out;
}
const chip = l => `<span class="chip ${l}">${({HAB:'Habitability',PAPER:'Paperwork',OTHER:'Other SDCI',FLAG:'Flag'})[l]||l}</span>`;
const bar = (v, max, lane) => `<div class="bar ${lane||''}"><span style="width:${Math.max(0.5,Math.min(100,100*v/(max||1)))}%"></span></div>`;
const sec = (id, title, sub, body) => `<section id="${id}"><h2>${title}</h2>${sub?`<p class="sub">${sub}</p>`:''}${body}</section>`;
const F = DATA.findings, M = DATA.meta;
const laneN = keys => DATA.lane_summary.filter(x=>keys.includes(x.key)).reduce((a,x)=>a+x.n,0);
const habN = DATA.lane_summary.filter(x=>x.key.includes('HAB')).reduce((a,x)=>a+x.n,0);
const paperN = DATA.lane_summary.filter(x=>x.key.includes('PAPER')).reduce((a,x)=>a+x.n,0);
const bothN = DATA.lane_summary.filter(x=>x.key.includes('HAB')&&x.key.includes('PAPER')).reduce((a,x)=>a+x.n,0);
const catRow = c => DATA.cats.find(x=>x.cat===c) || {nA:0};
const oldRow = (pop, name) => DATA.compare.find(x=>x.pop===pop && x.old_cat===name) || {};

// ------------------------------------------------------------------ header + toc
$('#hdr').innerHTML = `<h1>What the complaint descriptions actually say</h1>
<p>Habitability vs. landlord-tenant paperwork, built from the records themselves &mdash; every rule has an exact example and every match has a record ID.</p>
<p class="small">Source: <b>${esc(M.input_file)}</b> (sha256 ${esc(M.sha256.slice(0,12))}&hellip;) &middot; ${fmt(M.rows)} rows, ${fmt(M.complaints)} complaint records, ${fmt(M.with_text)} with description text &middot; opened ${esc(M.date_min)} to ${esc(M.date_max)} &middot; ${M.rules} rules &middot; built ${esc(M.built)}</p>
<p class="small mut">Internal review copy: phone numbers, e-mail addresses and links are masked in this page; names are not. The CSV files next to it hold the verbatim text.</p>`;
const TOC = [['bottom','Bottom line'],['old','Old script'],['new','New counts'],['who','Who wrote it'],['labels','City labels'],['rules','Rules + examples'],['vocab','Vocabulary'],['cmp','Old vs new'],['review','Manual review'],['none','No issue found'],['dist','Districts'],['next','Drill down'],['limits','Limits']];
$('#toc').innerHTML = TOC.map(([id,t])=>`<a href="#${id}">${t}</a>`).join('');

// ------------------------------------------------------------------ bottom line
(function(){
  const noIssue = (DATA.lane_summary.find(x=>x.key==='NO_ISSUE_WORDS')||{}).n||0;
  const inq = (DATA.lane_summary.find(x=>x.key==='INQUIRY_ONLY')||{}).n||0;
  const staff = (DATA.lane_summary.find(x=>x.key==='STAFF_NOTE_ONLY')||{}).n||0;
  const heatOld = oldRow('old_primary','HEAT'), evOld = oldRow('old_primary','NOTICE_EVICTION_DISPLACEMENT');
  const body = `<div class="cards">
   <div class="stat"><div class="n">${fmt(M.with_text)}</div><div class="l">complaint descriptions read (of ${fmt(M.complaints)} complaint records)</div></div>
   <div class="stat hab"><div class="n">${fmt(habN)}</div><div class="l">mention a habitability problem (${pc(100*habN/M.with_text)})</div></div>
   <div class="stat paper"><div class="n">${fmt(paperN)}</div><div class="l">mention a paperwork / landlord-tenant issue (${pc(100*paperN/M.with_text)})</div></div>
   <div class="stat"><div class="n">${fmt(bothN)}</div><div class="l">mention both in the same description</div></div>
   <div class="stat flag"><div class="n">${fmt(F.workflow+F.label_only)}</div><div class="l">are staff TRAO/EDRA workflow notes or contain only a city label (not tenant statements)</div></div>
   <div class="stat other"><div class="n">${fmt(inq)}</div><div class="l">are pure information requests ("what are my rights")</div></div>
   <div class="stat other"><div class="n">${fmt(noIssue)}</div><div class="l">have no issue words at all (${pc(100*noIssue/M.with_text)})</div></div>
  </div>
  <div class="card">
   <p><b>Why the old numbers swing.</b> The existing script counted heat in <b>${fmt(heatOld.n_old)}</b> and eviction/notice in <b>${fmt(evOld.n_old)}</b> of the <b>${fmt(F.n_old_primary)}</b> complaint records it reads. It only read ${fmt(F.n_old_primary)} of the ${fmt(F.n_rows)} rows (it drops the "review-only" rows and every non-complaint row), but <b>${fmt(F.hab_in_review_only)} of the ${fmt(F.hab_total)}</b> records with a habitability problem (${pc(100*F.hab_in_review_only/F.hab_total)}) sit in the review-only rows it dropped. Its heat phrases are narrow ("no heat", "heat is out"), while its eviction phrases are broad and its relocation category counts the city's own <b>TRAO</b>/<b>EDRA</b> labels as if a tenant had said them.</p>
   <p>Reading the descriptions with rules built from the records finds heat problems in <b>${fmt(catRow('HEAT').nA)}</b> complaint records (${pc(catRow('HEAT').pctA)}) and eviction/termination wording in <b>${fmt(catRow('EVICTION_TERMINATION').nA)}</b> (${pc(catRow('EVICTION_TERMINATION').pctA)}). Strict counts need wording in the text; the page also shows an inclusive range (borderline + city-label inferred).</p>
  </div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('bottom','Bottom line','Counts are complaint records; a record counts once per category, however many times the problem is repeated in it.', body));
})();

// ------------------------------------------------------------------ old script
(function(){
  const rows = DATA.compare.filter(x=>x.pop==='old_primary' && x.old_cat!=='SHA_PUBLIC_HOUSING_CONTEXT');
  const allr = o => DATA.compare.find(x=>x.pop==='all_complaints' && x.old_cat===o)||{};
  const mx = Math.max(...rows.map(r=>r.n_old));
  const tr = rows.sort((a,b)=>b.n_old-a.n_old).map(r=>`<tr><td>${esc(r.old_cat)}</td><td>${chip(r.lane==='FLAG'?'FLAG':r.lane)}</td><td class="num">${fmt(r.n_old)}</td><td>${bar(r.n_old,mx,r.lane)}</td><td class="num">${pc(100*r.n_old/r.n_pop)}</td><td class="num">${fmt(r.n_new)}</td><td class="num">${fmt(allr(r.old_cat).n_new)}</td><td class="num">${fmt(r.old_only)}</td><td class="num">${fmt(r.new_only)}</td></tr>`).join('');
  const rel = oldRow('old_primary','RELOCATION_ASSISTANCE');
  const body = `<p class="small">Population the script analysed: complaint records that are not "review-only" (${fmt(F.n_old_primary)} records; ${fmt(F.n_review_only)} review-only complaint rows and ${fmt(F.n_noncomplaint)} non-complaint rows were left out). Re-run here on the same JSON (sha256 matches the audit file).</p>
  <div class="tw"><table><thead><tr><th>Old category</th><th>Lane (my grouping)</th><th class="num">Old count</th><th></th><th class="num">% of its records</th><th class="num">New rules, same records</th><th class="num">New rules, all complaints</th><th class="num">Old only</th><th class="num">New only</th></tr></thead><tbody>${tr}</tbody></table></div>
  <ul class="find">
   <li><b>Wrong population for habitability.</b> ${fmt(F.hab_in_review_only)} of ${fmt(F.hab_total)} habitability records (${pc(100*F.hab_in_review_only/F.hab_total)}) are in the review-only rows the script excludes by default.</li>
   <li><b>City labels counted as tenant words.</b> ${fmt(rel.label_only)} of the ${fmt(rel.n_old)} records the old script put in RELOCATION_ASSISTANCE match only the acronym TRAO or EDRA. ${fmt(F.workflow)} complaint records are staff TRAO/EDRA workflow notes ("TRAO hold", "holding up permit #...") and ${fmt(F.label_only)} contain nothing but a label.</li>
   <li><b>Notice types lumped.</b> The old script counts any "N-day notice" as eviction/notice. Of the ${fmt(F.nday.total)} records with such a phrase, ${fmt(F.nday.evict)} have vacate / evict / terminate wording within 90 characters, ${fmt(F.nday.incr)} mention an increase, ${fmt(F.nday.entry)} mention entry or inspection, ${fmt(F.nday.repair)} mention repair or construction, and ${fmt(F.nday.none)} name none of these (a record can be in more than one group). The new rules read the words around the notice (see Old vs new).</li>
   <li><b>Notice-of-violation rows repeat the complaint.</b> ${fmt(F.vi_text_equals_a_complaint)} of ${fmt(F.vi_n)} NOV rows with text carry a description identical to a complaint's, so they are not independent evidence and are not counted again.</li>
  </ul>`;
  $('#app').insertAdjacentHTML('beforeend', sec('old','What the existing script showed','rare_district_story_parser.py run on the approved LLT JSON, split into habitability vs paperwork', body));
})();

// ------------------------------------------------------------------ new counts
(function(){
  const lanes = ['HAB','PAPER','OTHER'];
  const mx = Math.max(...DATA.cats.filter(c=>lanes.includes(c.lane)).map(c=>c.nA));
  const head = `<thead><tr><th>Category</th><th class="num">Records (strict)</th><th></th><th class="num">% of all</th><th class="num">Tenant wording only</th><th class="num">+ borderline</th><th class="num">+ city label</th><th class="num">Inclusive</th><th class="num">in review-only rows</th></tr></thead>`;
  const tbl = lane => `<h3>${esc(DATA.lane_label[lane])}</h3><div class="tw"><table>${head}<tbody>${DATA.cats.filter(c=>c.lane===lane).sort((a,b)=>b.nA-a.nA).map(c=>`<tr><td>${esc(c.label)}${/UNSPEC|SEVERITY/.test(c.cat)?' <span class="mut small">(not a separate issue)</span>':''}</td><td class="num">${fmt(c.nA)}</td><td>${bar(c.nA,mx,lane)}</td><td class="num">${pc(c.pctA)}</td><td class="num">${fmt(c.nT)}</td><td class="num">${fmt(c.nB)}</td><td class="num">${fmt(c.nL)}</td><td class="num">${fmt(c.nIncl)}</td><td class="num">${fmt(c.in_review_only)} <span class="mut small">(${pc(c.pct_in_review_only,0)})</span></td></tr>`).join('')}</tbody></table></div>`;
  const flags = DATA.cats.filter(c=>c.lane==='FLAG').sort((a,b)=>b.nA-a.nA).map(c=>`<tr><td>${esc(c.label)}</td><td class="num">${fmt(c.nA)}</td><td class="num">${pc(c.pctA)}</td><td class="num">${fmt(c.nT)}</td></tr>`).join('');
  const ls = DATA.lane_summary.map(x=>`<tr><td>${esc(DATA.lane_summary_labels[x.key]||x.key)}</td><td class="num">${fmt(x.n)}</td><td class="num">${pc(x.pct)}</td><td>${bar(x.n,DATA.lane_summary[0].n)}</td></tr>`).join('');
  const ih = DATA.issues_hist.map(x=>`<tr><td>${x.k} distinct issue${x.k==='1'?'':'s'}</td><td class="num">${fmt(x.n)}</td><td class="num">${pc(x.pct)}</td><td>${bar(x.n,Math.max(...DATA.issues_hist.map(h=>h.n)))}</td></tr>`).join('');
  const co = DATA.cooc.slice(0,14).map(x=>`<tr><td>${esc(x.a_label)} + ${esc(x.b_label)}</td><td class="num">${fmt(x.n)}</td></tr>`).join('');
  const body = `<div class="note"><b>Counting rule.</b> One record counts once per category (repeating "mold" five times is still one mold issue). Separate problems each count: "no heat, mold, broken plumbing" is three issues. "Strict" = wording found in the description. "Inclusive" adds borderline wording and categories inferred only from the city label in DESCRIPTION1. The true number sits between them.</div>
  ${tbl('HAB')}${tbl('PAPER')}${tbl('OTHER')}
  <h3>Flags &mdash; context, not issues</h3><div class="tw"><table><thead><tr><th>Flag</th><th class="num">Records</th><th class="num">% of all</th><th class="num">Tenant wording only</th></tr></thead><tbody>${flags}</tbody></table></div>
  <div class="grid2"><div><h3>Habitability vs paperwork, per description</h3><div class="tw"><table><thead><tr><th>Group</th><th class="num">Records</th><th class="num">%</th><th></th></tr></thead><tbody>${ls}</tbody></table></div></div>
  <div><h3>Separate issues per description</h3><div class="tw"><table><thead><tr><th>Issues</th><th class="num">Records</th><th class="num">% of records with an issue</th><th></th></tr></thead><tbody>${ih}</tbody></table></div>
  <h3>Issues that travel together</h3><div class="tw"><table><thead><tr><th>Pair</th><th class="num">Records</th></tr></thead><tbody>${co}</tbody></table></div></div></div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('new','Habitability vs paperwork: new counts','Habitability is both a landlord-tenant issue and an SDCI housing-code issue; paperwork is landlord-tenant law only.', body));
})();

// ------------------------------------------------------------------ who wrote it
(function(){
  const eras = DATA.eras;
  const rows = DATA.authorship.map(a=>`<tr><td>${esc(a.label)}</td><td class="num">${fmt(a.n)}</td><td class="num">${pc(a.pct)}</td>${eras.map(e=>`<td class="num">${pc(a.era[e],0)}</td>`).join('')}<td class="num">${pc(a.glue_pct)}</td><td class="ex">${a.example?`<span class="id">${esc(a.example.id)}</span> ${esc(a.example.text)}`:''}</td></tr>`).join('');
  const ten = DATA.authorship.find(a=>a.cls==='TENANT_FIRST_PERSON')||{}, ph = DATA.authorship.find(a=>a.cls==='STAFF_PHONE_SUMMARY')||{}, on = DATA.authorship.find(a=>a.cls==='ONLINE_FORM_TEXT')||{};
  const body = `<div class="note">The record does not say who typed DESCRIPTION. These classes come from markers inside the text, so they are evidence, not proof. One pattern that points the same way: some words are run together ("rentincrease"), and only ${fmt(F.desc_with_linebreak)} of ${fmt(F.n_complaints)} descriptions still contain a line break, so the run-together words look like dropped line breaks (inferred, not checked against the source system). Run-together words occur in ${pc(ten.glue_pct)} of first-person records but only ${pc(ph.glue_pct)} of staff phone summaries, which fits first-person text coming from a form field and phone summaries being typed by staff (a pattern, not proof).</div>
  <div class="tw"><table><thead><tr><th>Text looks like</th><th class="num">Records</th><th class="num">%</th>${eras.map(e=>`<th class="num">${e}</th>`).join('')}<th class="num">Fused-word %</th><th>Example</th></tr></thead><tbody>${rows}</tbody></table></div>
  <ul class="find"><li>The share in first-person tenant wording (I / my / we) rises from ${pc((ten.era||{})[eras[0]],0)} (${eras[0]}) to ${pc((ten.era||{})[eras[eras.length-1]],0)} (${eras[eras.length-1]}).</li>
  <li>Counts in this page include every class; the "Tenant wording only" column in the counts table uses just first-person and online-form text (${fmt((ten.n||0)+(on.n||0))} records).</li>
  <li>City labels (POTA, JCEO, TRAO, EDRA ...) are masked before matching so they can never count as tenant vocabulary; they are tallied separately below.</li></ul>`;
  $('#app').insertAdjacentHTML('beforeend', sec('who','Is the text tenant-reported or staff-entered?','DESCRIPTION is the primary text; DESCRIPTION1 holds the city labels and staff notes.', body));
})();

// ------------------------------------------------------------------ city labels
(function(){
  const rows = DATA.labels.map(l=>`<tr><td><b>${esc(l.label)}</b></td><td class="num">${fmt(l.n)}</td><td class="num">${pc(l.pct_hab,0)}</td><td class="num">${pc(l.pct_paper,0)}</td><td class="num">${pc(l.pct_other,0)}</td><td class="num">${pc(l.pct_none,0)}</td><td class="small">${l.top.slice(0,3).map(t=>esc(catName(t[0]))+' '+Math.round(t[1])+'%').join('; ')}</td><td class="small">${l.inferred?esc(l.inferred)+' <span class="mut">('+l.inferred_share+'%)</span>':'<span class="mut">not used</span>'}</td></tr>`).join('');
  const body = `<p class="small">A label is used to fill in a category only when at least 75% of the records carrying it, among those where the text does show a category, fall in that category or lane. It is shown as "label-inferred" and never mixed into the strict counts. The meaning of a code is read from what the descriptions with that code say, not assumed.</p>
  <div class="tw"><table><thead><tr><th>Label in DESCRIPTION1</th><th class="num">Records</th><th class="num">Hab. %</th><th class="num">Paper %</th><th class="num">Other %</th><th class="num">Nothing found %</th><th>What the text says most often</th><th>Used to infer</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('labels','City labels (DESCRIPTION1) checked against the tenant text','Independent check on the rules: records labelled HOUSING should read as habitability, INRENT as rent increases, and so on.', body));
})();

// ------------------------------------------------------------------ rules
(function(){
  const body = `<div class="tools"><input id="rq" type="search" placeholder="Filter rules (id, category, wording)" size="34"><select id="rl"><option value="">All lanes</option><option value="HAB">Habitability</option><option value="PAPER">Paperwork</option><option value="OTHER">Other SDCI</option><option value="FLAG">Flags</option></select><span class="mut small" id="rc"></span></div>
  <div class="tw"><table id="rt"><thead><tr><th>Rule</th><th>What it catches</th><th class="num">Records</th><th>Exact example from the records</th></tr></thead><tbody></tbody></table></div>
  <details><summary>Why matches were rejected (negation, overlap, context)</summary><div class="tw"><table><thead><tr><th>Decision</th><th>Rule</th><th>Record</th><th>Context</th><th>Reason</th></tr></thead><tbody>${DATA.reject_examples.map(e=>`<tr><td>${esc(e.decision)}</td><td>${esc(e.rule)}</td><td class="mono">${esc(e.id)}</td><td class="ex">${esc(e.snippet).replace('[[','<mark>').replace(']]','</mark>')}</td><td class="small">${esc(e.reason)}</td></tr>`).join('')}</tbody></table></div></details>`;
  $('#app').insertAdjacentHTML('beforeend', sec('rules','Every rule, with an exact example','Examples are copied from the records (whitespace normalised). The rule must reproduce its own example every time the script starts (self-test).', body));
  const draw = () => {
    const q = $('#rq').value.toLowerCase(), ln = $('#rl').value;
    const rs = DATA.rules.filter(r => (!ln || r.lane===ln) && (!q || (r.id+' '+r.cat+' '+r.cat_label+' '+r.desc+' '+r.example_text).toLowerCase().includes(q)));
    $('#rc').textContent = rs.length + ' of ' + DATA.rules.length + ' rules';
    $('#rt tbody').innerHTML = rs.map(r=>`<tr><td><b>${esc(r.id)}</b><br>${chip(r.lane)}<br><span class="small mut">${esc(r.kind)}</span></td>
      <td>${esc(r.cat_label)}<br><span class="small">${esc(r.desc)}</span><details><summary class="small">pattern</summary><pre class="pat">${esc(r.pattern)}${r.cue?'\n+ cue: '+esc(r.cue):''}${r.cue2?'\n+ near cue: '+esc(r.cue2):''}</pre></details></td>
      <td class="num small">${fmt(r.records_accept)} accepted<br>${fmt(r.records_borderline)} borderline<br>${fmt(r.rejected_negated+r.rejected_overlap+r.rejected_context)} rejected</td>
      <td class="ex">${r.example_id?`<span class="id">${esc(r.example_id)} &middot; ${esc(r.example_decision)}${r.self_test==='PASS'?' &middot; <span class="chip ok">self-test pass</span>':(r.self_test==='FAIL'?' &middot; <span class="chip bad">self-test FAIL</span>':'')}</span><br>${hl(r.example_text, r.example_phrase)}`:'<span class="mut">no example in these records</span>'}</td></tr>`).join('');
  };
  $('#rq').addEventListener('input', draw); $('#rl').addEventListener('change', draw); draw();
})();

// ------------------------------------------------------------------ vocabulary
(function(){
  const mk = (id, head, rows) => `<div class="tw"><table><thead><tr>${head.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
  const ms = mk('m',['Written as','Means','Records','Example'], DATA.misspell.map(m=>`<tr><td><b>${esc(m.variant)}</b></td><td>${esc(m.canonical)}</td><td class="num">${fmt(m.records)}</td><td class="ex"><span class="id">${esc(m.example_id)}</span> ${esc(m.example).replace('[[','<mark>').replace(']]','</mark>')}</td></tr>`).join(''));
  const sh = mk('s',['Shorthand','Meaning','How known','Records','Example'], DATA.shorthand.map(m=>`<tr><td><b>${esc(m.token)}</b></td><td>${esc(m.meaning)}</td><td class="small">${esc(m.how_known)}</td><td class="num">${fmt(m.records)}</td><td class="ex"><span class="id">${esc(m.example_id)}</span> ${esc(m.example).replace('[[','<mark>').replace(']]','</mark>')}</td></tr>`).join(''));
  const fu = mk('f',['Fused word','Repaired to','Records','Example'], DATA.fused.map(m=>`<tr><td><b>${esc(m.fused_token)}</b></td><td>${esc(m.split)}</td><td class="num">${fmt(m.records)}</td><td class="ex"><span class="id">${esc(m.example_id)}</span> ${esc(m.example).replace('[[','<mark>').replace(']]','</mark>')}</td></tr>`).join(''));
  const inf = mk('i',['Wording','Group','Records','Example'], DATA.informal.map(m=>`<tr><td><b>${esc(m.phrase)}</b></td><td class="small">${m.category==='INFORMAL_SLANG'?'slang / colloquial':'profanity / insult'}</td><td class="num">${fmt(m.records)}</td><td class="ex"><span class="id">${esc(m.example_id)}</span> ${esc(m.example).replace('[[','<mark>').replace(']]','</mark>')}</td></tr>`).join(''));
  const slangN = (DATA.cats.find(c=>c.cat==='INFORMAL_SLANG')||{}).nA||0, profN = (DATA.cats.find(c=>c.cat==='PROFANITY_OR_INSULT')||{}).nA||0;
  const lg = F.lang||{}; const es = lg.es||0;
  const tabs = {Misspellings:ms, Shorthand:sh, 'Fused words':fu, 'Slang and profanity':inf};
  const body = `<div class="note"><b>How much slang is there?</b> Slang or colloquial wording appears in ${fmt(slangN)} records (${pc(100*slangN/M.with_text)}) and profanity or insults in ${fmt(profN)} (${pc(100*profN/M.with_text)}). It is real but small. The swings in the old numbers come from what the old script did (narrow phrases, the review-only filter, city labels counted as words; see "What the existing script showed"). Other wording variation handled here: run-together words (${fmt(M.glue_repairs)} repaired using the records), city labels inside the text, staff shorthand. Non-English text: ${fmt(es)} Spanish-looking records (word-list guess); the English rules will mostly miss them.</div>
  <div class="tools tabs" id="vt">${Object.keys(tabs).map((k,i)=>`<button data-k="${k}" class="${i?'':'on'}">${k}</button>`).join('')}</div><div id="vb"></div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('vocab','Vocabulary built from the records','Misspellings, shorthand, fused words and slang that actually occur, each with an example. Full phrase-level list: vocab_terms_observed.csv.', body));
  const show = k => { $('#vb').innerHTML = tabs[k]; document.querySelectorAll('#vt button').forEach(b=>b.classList.toggle('on', b.dataset.k===k)); };
  document.querySelectorAll('#vt button').forEach(b=>b.addEventListener('click', ()=>show(b.dataset.k))); show(Object.keys(tabs)[0]);
})();

// ------------------------------------------------------------------ old vs new
(function(){
  const rows = DATA.compare.filter(x=>x.pop==='all_complaints');
  const items = rows.sort((a,b)=>b.n_old-a.n_old).map(c=>`<details class="card"><summary><b>${esc(c.old_cat)}</b> &mdash; old ${fmt(c.n_old)} &middot; new ${fmt(c.n_new)} &middot; both ${fmt(c.both)} &middot; old only ${fmt(c.old_only)} &middot; new only ${fmt(c.new_only)}</summary>
    <p class="small mut">New rules compared: ${c.new_targets.map(esc).join(', ')||'none'} (${esc(c.kind)}). Records the old category flagged contain: ${c.composition.map(x=>esc(catName(x[0]))+' '+fmt(x[1])).join('; ')||'-'}${c.label_only?`. Of the old flags, <b>${fmt(c.label_only)}</b> are only the acronym TRAO/EDRA.`:''}</p>
    <div class="grid2"><div><b class="small">Old flagged, new rules did not</b>${c.ex_old.map(e=>`<p class="ex"><span class="id">${esc(e.id)} &middot; old matched "${esc(e.phrase)}"</span><br>${esc(e.text)}</p>`).join('')||'<p class="mut small">none with a shareable example</p>'}</div>
    <div><b class="small">New rules flagged, old did not</b>${c.ex_new.map(e=>`<p class="ex"><span class="id">${esc(e.id)} &middot; new: ${e.new.map(catName).map(esc).join(', ')}</span><br>${esc(e.text)}</p>`).join('')||'<p class="mut small">none with a shareable example</p>'}</div></div></details>`).join('');
  $('#app').insertAdjacentHTML('beforeend', sec('cmp','Old script vs new rules, category by category','Counts are over all complaint records with text. Open a category for examples where the two disagree; every disagreement, with its record ID, is in old_vs_new_all_disagreements.csv.', items));
})();

// ------------------------------------------------------------------ manual review pocket
(function(){
  const pcnt = DATA.pocket_counts.slice(0,14).map(([c,n])=>`<tr><td>${esc(catName(c))}</td><td class="num">${fmt(n)}</td></tr>`).join('');
  const rows = DATA.pocket_sample.map((p,i)=>`<tr data-i="${i}"><td class="mono">${esc(p.id)}</td><td>${esc(p.label)}</td><td class="small">${esc(p.phrase)}<br><span class="mut">${esc(p.reason)}</span></td><td class="ex">${esc(p.text)}</td><td><select data-i="${i}"><option value=""></option><option>ACCEPT</option><option>REJECT</option></select></td></tr>`).join('');
  const body = `<p>Borderline means the wording is real but ambiguous on its own (a bare word like "fee", "privacy", "elevator", or a city label with no matching words). They are <b>not</b> in the strict counts. ${fmt(DATA.pocket_total)} record-category pairs are waiting; this page shows ${fmt(DATA.pocket_sample.length)} (up to 10 per category). The full list is manual_review_pocket.csv.</p>
  <div class="grid2"><div class="tw"><table><thead><tr><th>Category</th><th class="num">Pairs to review</th></tr></thead><tbody>${pcnt}</tbody></table></div>
  <div class="card small">Pick ACCEPT or REJECT, then <b>Download decisions</b>. Save the file next to the JSON and run the script with <code>--decisions decisions.csv</code>; accepted pairs move into the strict counts, rejected ones disappear, and the file is applied each time you rerun with --decisions.</div></div>
  <div class="tools"><button class="pri" id="dl">Download decisions (CSV)</button><span class="mut small" id="dc">0 decisions</span></div>
  <div class="tw" style="max-height:620px;overflow:auto"><table><thead><tr><th>Record</th><th>Category</th><th>Wording and why</th><th>Description</th><th>Decision</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('review','Borderline cases: the manual review pocket','Nothing here is forced into a category.', body));
  const dec = {};
  document.querySelectorAll('#review select').forEach(s=>s.addEventListener('change', ()=>{ dec[s.dataset.i]=s.value; $('#dc').textContent = Object.values(dec).filter(Boolean).length + ' decisions'; }));
  $('#dl').addEventListener('click', ()=>{
    const q = v => '"'+String(v).replace(/"/g,'""')+'"';
    const lines = ['record_id,category,decision'];
    Object.entries(dec).forEach(([i,d])=>{ if(d){ const p = DATA.pocket_sample[i]; lines.push([q(p.id),q(p.cat),q(d)].join(',')); } });
    const blob = new Blob([lines.join('\r\n')], {type:'text/csv'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'decisions.csv'; a.click();
  });
})();

// ------------------------------------------------------------------ no issue found
(function(){
  const rows = Object.entries(DATA.unmatched_counts).sort((a,b)=>b[1]-a[1]).map(([k,n])=>`<tr><td>${esc(AL[k]||k)}</td><td class="num">${fmt(n)}</td><td class="num">${pc(100*n/DATA.unmatched_total)}</td></tr>`).join('');
  const smp = DATA.unmatched_sample.map(u=>`<tr><td class="mono">${esc(u.id)}</td><td class="small">${esc(AL[u.author]||u.author)}</td><td class="small">${esc(u.labels)}</td><td class="ex">${esc(u.text)}</td></tr>`).join('');
  const body = `<p>${fmt(DATA.unmatched_total)} descriptions contain no issue wording after all rules (and are not pure information requests or staff notes). Reading a sample is how missing vocabulary gets found: each real miss becomes a new rule with its own example. All of them are in unmatched_statements.csv.</p>
  <div class="grid2"><div class="tw"><table><thead><tr><th>Text looks like</th><th class="num">Records</th><th class="num">%</th></tr></thead><tbody>${rows}</tbody></table></div><div class="card small">Many are genuinely empty of an issue (a name, "see attached", a one-word label). Some are real misses written in unusual wording; those are the ones to turn into rules.</div></div>
  <div class="tw" style="max-height:520px;overflow:auto"><table><thead><tr><th>Record</th><th>Text looks like</th><th>City label</th><th>Description</th></tr></thead><tbody>${smp}</tbody></table></div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('none','Descriptions where no issue was found','The remaining gap, listed so it can be closed from evidence.', body));
})();

// ------------------------------------------------------------------ districts
(function(){
  const D = DATA.districts, ds = D.districts;
  const pairOf = (a,b) => D.pairs.find(p=>(p.a===a&&p.b===b)||(p.a===b&&p.b===a));
  const mads = D.pairs.map(p=>p.mad_pp), lo = Math.min(...mads), hi = Math.max(...mads);
  const shade = v => { const t = (v-lo)/((hi-lo)||1); const a = 0.15+0.6*(1-t); return `rgba(15,118,110,${a.toFixed(2)})`; };
  const mat = `<table class="matrix"><thead><tr><th></th>${ds.map(d=>`<th>D${d}</th>`).join('')}</tr></thead><tbody>${ds.map(a=>`<tr><th>D${a}</th>${ds.map(b=>a===b?'<td class="self">&ndash;</td>':`<td data-a="${a}" data-b="${b}" style="background:${shade(pairOf(a,b).mad_pp)}">${pairOf(a,b).mad_pp.toFixed(2)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const sorted = D.pairs.slice().sort((x,y)=>x.mad_pp-y.mad_pp);
  const pl = sorted.map(p=>`<tr data-a="${p.a}" data-b="${p.b}" style="cursor:pointer"><td>D${p.a} &amp; D${p.b}</td><td class="num">${p.mad_pp.toFixed(2)}</td><td class="num">${p.cosine.toFixed(3)}</td><td class="small">${p.alike.slice(0,2).map(x=>esc(catName(x.cat))+' ('+x.a_std.toFixed(1)+'% vs '+x.b_std.toFixed(1)+'%)').join('; ')}</td><td class="small">${p.different.slice(0,2).map(x=>esc(catName(x.cat))+' ('+x.a_std.toFixed(1)+'% vs '+x.b_std.toFixed(1)+'%)').join('; ')}</td></tr>`).join('');
  const sig = ds.map(d=>{ const s = D.signature[d]; const t = D.table.find(x=>x.district===d); return `<tr><td><b>D${d}</b></td><td class="num">${fmt(t.n)}</td><td class="small">${s.higher.slice(0,3).map(x=>esc(catName(x.cat))+' '+x.rate.toFixed(1)+'% (others '+x.others.toFixed(1)+'%)').join('<br>')}</td><td class="small">${s.lower.slice(0,3).map(x=>esc(catName(x.cat))+' '+x.rate.toFixed(1)+'% (others '+x.others.toFixed(1)+'%)').join('<br>')}</td></tr>`; }).join('');
  const body = `<p class="small">Rates are the share of a district's complaint descriptions with the category. They are shown raw and year-standardised (each district reweighted to the citywide mix of years, because the years differ in how complaints were recorded). ${fmt(D.n_unknown)} records have no district and are left out. Differences are descriptive: they are not adjusted for rental units, reporting habits or label coverage.</p>
  <div class="grid2"><div><h3>How alike each pair is (smaller = more alike)</h3><p class="small mut">Mean gap in percentage points across ${D.cats.length} issue categories, year-standardised. Click a cell.</p>${mat}</div>
  <div id="pd" class="card small"><b>Pick a pair</b> from the grid or the table to see where it matches and where it differs.</div></div>
  <h3>All 21 pairs, most alike first</h3><div class="tw"><table><thead><tr><th>Pair</th><th class="num">Mean gap (pp)</th><th class="num">Cosine</th><th>Most alike on</th><th>Most different on</th></tr></thead><tbody>${pl}</tbody></table></div>
  <h3>What stands out in each district</h3><div class="tw"><table><thead><tr><th>District</th><th class="num">Records</th><th>Higher than the other six</th><th>Lower than the other six</th></tr></thead><tbody>${sig}</tbody></table></div>`;
  $('#app').insertAdjacentHTML('beforeend', sec('dist','Districts, paired with each other','How much any two council districts are alike and where they differ.', body));
  const show = (a,b) => {
    const p = pairOf(a,b); if(!p) return; const flip = p.a!==a;
    const row = x => { const A = flip?x.b_std:x.a_std, B = flip?x.a_std:x.b_std; return `<tr><td>${esc(catName(x.cat))}</td><td class="num">${A.toFixed(1)}%</td><td class="num">${B.toFixed(1)}%</td><td class="num">${(flip?-x.z:x.z).toFixed(1)}</td></tr>`; };
    const t = rows => `<div class="tw"><table><thead><tr><th>Category</th><th class="num">D${a}</th><th class="num">D${b}</th><th class="num">z</th></tr></thead><tbody>${rows.map(row).join('')}</tbody></table></div>`;
    $('#pd').innerHTML = `<b>District ${a} &amp; District ${b}</b> &middot; mean gap ${p.mad_pp.toFixed(2)} pp &middot; cosine ${p.cosine.toFixed(3)}<h4>Most alike</h4>${t(p.alike)}<h4>Most different</h4>${t(p.different)}<p class="mut">z compares the raw counts (|z| above 3 is unlikely to be chance alone).</p>`;
  };
  document.querySelectorAll('#dist [data-a]').forEach(el=>el.addEventListener('click', ()=>show(el.dataset.a, el.dataset.b)));
  show(sorted[0].a, sorted[0].b);
})();

// ------------------------------------------------------------------ drill down + limits
(function(){
  const nxt = `<ol>
   <li><b>Read the "no issue found" list and the borderline pocket, then rerun.</b> Keep decisions.csv and pass it with --decisions on every rerun so earlier decisions are applied again; the rules then improve from evidence instead of from a growing guess list.</li>
   <li><b>Add a 300-record hand-labelled sample.</b> Label a random sample (stratified by year) for the lanes and categories; that would let precision and recall be measured for each rule. The script does not do this yet; for now the checks are the city-label cross-check and reading samples.</li>
   <li><b>Link complaints to the notices of violation at the same address.</b> If an NOV within a year names the same category, that complaint is corroborated by the city's own finding. NOV description text is not usable for this (it often repeats the complaint), so use the violation record's code and status instead.</li>
   <li><b>Collapse repeat filings.</b> ${fmt(F.repeat_records)} records sit in ${fmt(F.repeat_groups)} groups with identical text at the same address and date; these could count once as "unique complaint events". record_issues.csv has the address and date for this.</li>
   <li><b>Report rates, not totals.</b> Divide district counts by rental units before comparing districts, and compare years only within a recording era: the "Per phone" wrapper appears almost only in 2013-2019 and the "Per online" wrapper stops after 2023 (counts by year from the channel column of record_issues.csv).</li>
   <li><b>Add severity and duration.</b> "No response" and "making me sick" are already captured as flags; duration wording ("for three months") is not captured yet. Sorting the habitability lane by these would surface the cases that matter most.</li>
   <li><b>Translate non-English entries.</b> ${fmt((F.lang||{}).es||0)} records look Spanish (word-list guess); the English rules will mostly miss them.</li>
   <li><b>Get the 2026 file.</b> Only the approved file through 2025-12-31 was read. The 2026 JSON named in README_RUN_AND_PROVENANCE.md (LLT_20260101_THROUGH_20261001.json) was not in the data folder or the KEYWORDS folder.</li></ol>`;
  const lim = `<ul class="find"><li>A match means the words appear in the description. It does not prove the condition existed, that a violation occurred, or who wrote the text.</li>
   <li>Authorship classes come from markers in the text. Some wording is run together (probably dropped line breaks; inferred); ${fmt(M.glue_repairs)} such tokens were repaired using the records themselves (listed in vocab_fused_words.csv).</li>
   <li>"Habitability" and "paperwork" are my grouping of categories (see the rules table), not the City's. Whether a category is enforceable by SDCI is not decided here.</li>
   <li>The meaning of city codes (INRENT, RENTAG, PAOTHR, RARO, EDRA ...) is inferred from the text that carries them and is labelled as inferred.</li>
   <li>Counts cover complaint records only. Notice-of-violation, citation, unfit-building and relocation-license rows are other record types and are not added.</li></ul>`;
  $('#app').insertAdjacentHTML('beforeend', sec('next','How to drill down further','', nxt) + sec('limits','What this does and does not show','', lim));
  $('#foot').innerHTML = `Built ${esc(M.built)} by llt_issue_rules.py v${esc(M.version)}. Files: ${esc(M.out)}, rules_with_examples.csv, match_audit.csv, record_issues.csv, vocab_*.csv, city_labels.csv, manual_review_pocket.csv, unmatched_statements.csv, old_vs_new_*.csv, district_*.csv.`;
})();
</script>
</body>
</html>
'''


README_TEXT = """# LLT vocabulary audit - how to read this folder

Open LLT_vocab_audit.html first. Everything else is the audit trail behind it.

* rules_with_examples.csv  - one row per rule with an exact example record
* match_audit.csv          - every match and every rejection (record ID, decision, reason, phrase, context)
* record_issues.csv        - one row per complaint: authorship, lane, categories, distinct issues, text
* manual_review_pocket.csv - borderline cases. Fill the 'decision' column with ACCEPT or REJECT, save as
                             decisions.csv (columns: record_id, category, decision) and rerun with --decisions
* unmatched_statements.csv - descriptions with no issue wording (where new rules come from)
* old_vs_new_all_disagreements.csv - every complaint where the old script and these rules disagree (record ID, old phrase, new categories)
* vocab_*.csv, city_labels.csv, old_vs_new_*.csv, district_*.csv - vocabulary, label checks, comparisons

Definitions
* strict count   = wording found in the description (ACCEPT)
* inclusive      = strict + borderline wording + categories inferred only from the city label (DESCRIPTION1)
* lane           = habitability (landlord-tenant AND SDCI housing code) / paperwork (landlord-tenant law) / other SDCI
"""

def main(argv=None):
    ap = argparse.ArgumentParser(description='Evidence-built issue rules for LLT complaint descriptions (read-only on the JSON).')
    ap.add_argument('input_json'); ap.add_argument('--out', default='llt_vocab_audit')
    ap.add_argument('--parser-dir', default=None); ap.add_argument('--decisions', default=None)
    ap.add_argument('--workers', type=int, default=None); ap.add_argument('--self-test-only', action='store_true')
    a = ap.parse_args(argv)
    st = self_test(RULES, EXAMPLES, analyze) if EXAMPLES else {}
    fails = sorted(k for k, v in st.items() if v == 'FAIL')
    print('self-test: %d rules, %d pass, %d fail, %d without example' % (len(RULES), sum(v == 'PASS' for v in st.values()), len(fails), sum(v == 'NO_EXAMPLE' for v in st.values()) + (len(RULES) - len(st))))
    if fails:
        print('RULES THAT NO LONGER REPRODUCE THEIR EXAMPLE:', ', '.join(fails)); sys.exit(3)
    if a.self_test_only: return
    parser_dir = a.parser_dir or os.path.dirname(os.path.abspath(__file__))
    B = run_all(a.input_json, a.out, parser_dir, a.decisions, a.workers, EXAMPLES or None)
    p, size = write_html(B, a.out, 'LLT_vocab_audit.html', HTML_TEMPLATE)
    open(os.path.join(a.out, 'README.md'), 'w', encoding='utf-8').write(README_TEXT)
    try: shutil.copy2(os.path.abspath(__file__), os.path.join(a.out, 'llt_issue_rules.py'))
    except Exception: pass
    print('wrote', p, '(%d KB)' % (size // 1024))

if __name__ == '__main__':
    main()
