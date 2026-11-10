#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_district_maps.py - writes district-1-map.html ... district-7-map.html

Each page is one static file (CSS, JS and data inline; no CDN, no map tiles). Each page shows the WHOLE CITY on two maps side by side
(habitability on the left, paperwork / landlord-tenant law on the right); the page's own district is in full color and carries the
details (address, categories, related complaints), the rest of the city is faded context.

Reads (never writes) - all inside the 'source' folder next to this file, nothing outside the website folder:
  source/LLT_APPROVED_THROUGH_20251231.json     complaint records: coordinates, district, date, status, address
  source/record_issues.csv (vocabulary audit)   the problem categories found in each complaint description, plus the description text
  source/match_audit.csv                        the exact words the audit matched for each problem type (written into the CSV files)
  source/ALL_UNITS_GEO_CENTROID_*.csv           residential properties (gray base dots) and neighbourhood names for labels
  source/seattle_council_districts_CURRENT.geojson   the seven council district outlines (land fill and borders)
  source/Building_Outlines_2023.geojson          City of Seattle building outlines 2023 (optional: without it the pages have no buildings)
Writes only the seven pages and their seven record CSVs (district-N-map-records.csv) into the 'pages' folder next to this file (or into the folder given as the first argument, for test builds).

    python build_district_maps.py [output_folder]
"""
import csv, hashlib, json, math, os, re, sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, 'pages')
SRC = os.path.join(HERE, 'source')      # every file the builder reads lives here, inside the website folder
JSON_PATH = os.path.join(SRC, 'LLT_APPROVED_THROUGH_20251231.json')
AUDIT_CSV = os.path.join(SRC, 'record_issues.csv')
MATCH_CSV = os.path.join(SRC, 'match_audit.csv')
AUDIT_NAME = 'LLT_VOCAB_AUDIT_20261018'  # the vocabulary audit these problem types come from (shown on the page)
UNITS_CSV = os.path.join(SRC, 'ALL_UNITS_GEO_CENTROID_-7156434836825490772.csv')
GEO_PATH = os.path.join(SRC, 'seattle_council_districts_CURRENT.geojson')   # official council district outlines (EPSG:4326)
BLD_PATH = os.path.join(SRC, 'Building_Outlines_2023.geojson')   # City of Seattle 'Building Outlines 2023' (SeattleData open data), EPSG:4326
BLD_NAME = 'City of Seattle Building Outlines 2023'
BLD_NEAR_M = 10      # a complaint point outside every outline joins the nearest outline only when its edge is within this many meters
BLD_CELL = 0.0005    # grid cell (degrees) for finding outlines near a point
BLD_Q = 1e6          # building corners stored in 1e-6 degree units (about 0.1 m)
LINK_BASE = 'https://services.seattle.gov/portal/customize/LinkToRecord.aspx?altId='
LAT0, LON0 = 47.45, -122.45

# legend groups. Order = colour priority inside a lane (a complaint takes the colour of the first group it belongs to).
GROUPS = [
    ('FIRE',   'Fire, smoke/CO alarms, gas',                   '#d4007f', 'H'),
    ('STRUCT', 'Structural, doors, windows',                   '#a3321f', 'H'),
    ('HEAT',   'Heat, hot water, utilities',                   '#27b3e6', 'H'),
    ('WATER',  'Mold, leaks, moisture',                        '#1f6fd0', 'H'),
    ('PLUMB',  'Plumbing, sewage',                             '#e08600', 'H'),
    ('ELEC',   'Electrical',                                   '#12935a', 'H'),
    ('PEST',   'Pests',                                        '#7a4fb8', 'H'),
    ('OTHERH', 'Other housing conditions',                     '#8c8c1f', 'H'),
    ('P3DAY',  '3-day notices',                                '#0072b2', 'P'),
    ('PJCEO',  'Just cause eviction (JCEO)',                   '#7a1f3d', 'P'),
    ('PEVICT', 'Evictions and termination',                    '#d55e00', 'P'),
    ('PRENT',  'Rent increases and fees',                      '#009e73', 'P'),
    ('PDEP',   'Deposits and refunds',                         '#8e2d9e', 'P'),
    ('PNOTE',  'Other notices (type not stated)',              '#2fb4c9', 'P'),
    ('PLEASE', 'Lease terms and renewals',                     '#d9a400', 'P'),
    ('POTH',   'Other (retaliation, entry, relocation, lockouts)', '#cc79a7', 'P'),
    ('OTHER',  'Other (noise, construction, public space)',    '#9a7b4f', 'O'),
    ('UNAS',   'Unassigned',                                   '#000000', 'U'),
]
GIDX = {g[0]: i for i, g in enumerate(GROUPS)}
CAT_GROUP = {
    'FIRE_SMOKE_CO_GAS': 'FIRE',
    'STRUCTURAL': 'STRUCT', 'DOORS_WINDOWS_SECURITY': 'STRUCT',
    'HEAT': 'HEAT', 'HOT_WATER': 'HEAT', 'WATER_SERVICE': 'HEAT', 'UTILITY_SERVICE_LOSS': 'HEAT', 'HVAC_COOLING': 'HEAT',
    'MOLD_MOISTURE': 'WATER', 'LEAKS_WATER_INTRUSION': 'WATER',
    'PLUMBING_SEWAGE': 'PLUMB', 'ELECTRICAL': 'ELEC', 'PESTS': 'PEST',
    'ELEVATOR_ACCESS': 'OTHERH', 'SANITATION_ODOR': 'OTHERH', 'HAZMAT_AIR': 'OTHERH', 'APPLIANCES_FIXTURES': 'OTHERH',
    'OVERCROWDING': 'OTHERH', 'HAB_UNSPECIFIED': 'OTHERH', 'UNINHABITABLE_SEVERITY': 'OTHERH',
    'EVICTION_TERMINATION': 'PEVICT', 'RENT_INCREASE_FEES': 'PRENT', 'DEPOSIT_RETURN': 'PDEP', 'NOTICE_UNSPECIFIED': 'PNOTE',
    'LEASE_TERMS': 'PLEASE',
    'RETALIATION_HARASSMENT': 'POTH', 'ENTRY_PRIVACY': 'POTH', 'RELOCATION_DISPLACEMENT': 'POTH', 'LOCKOUT_SELF_HELP': 'POTH',
    'DISCRIMINATION': 'POTH', 'REGISTRATION_PAPERWORK': 'POTH', 'RENT_PAYMENT_DISPUTE': 'POTH', 'UTILITY_BILLING': 'POTH',
    'NOISE_NUISANCE': 'OTHER', 'CONSTRUCTION_PERMIT': 'OTHER', 'PUBLIC_SPACE': 'OTHER', 'NEIGHBOR_BEHAVIOR': 'OTHER', 'ZONING_USE': 'OTHER',
    'NOTICE_3DAY': 'P3DAY',          # found by wording in DESCRIPTION or DESCRIPTION1 (THREE_DAY below), not by the audit rules
    'JCEO_CASE': 'PJCEO',            # the City's JCEO label, or "just cause" wording (see below), not by the audit rules
}
CAT_LABEL = {
    'HEAT': 'Heat', 'HOT_WATER': 'Hot water', 'WATER_SERVICE': 'Water service, pressure, quality', 'LEAKS_WATER_INTRUSION': 'Leaks, flooding, water intrusion',
    'PLUMBING_SEWAGE': 'Plumbing and sewage', 'MOLD_MOISTURE': 'Mold and moisture', 'PESTS': 'Pests (bed bugs, roaches, rodents)', 'ELECTRICAL': 'Electrical and power',
    'STRUCTURAL': 'Structural / building envelope', 'DOORS_WINDOWS_SECURITY': 'Doors, windows, locks, mail, security', 'FIRE_SMOKE_CO_GAS': 'Fire, smoke/CO alarms, gas, exits',
    'ELEVATOR_ACCESS': 'Elevator and accessibility', 'SANITATION_ODOR': 'Sanitation, trash, odors', 'HAZMAT_AIR': 'Hazardous materials, fumes, ventilation',
    'APPLIANCES_FIXTURES': 'Appliances and fixtures', 'HVAC_COOLING': 'Air conditioning / HVAC (cooling)', 'UTILITY_SERVICE_LOSS': 'Gas / utility service loss',
    'OVERCROWDING': 'Overcrowding / occupancy', 'HAB_UNSPECIFIED': 'General habitability (no defect named)', 'UNINHABITABLE_SEVERITY': 'Uninhabitable / unfit',
    'EVICTION_TERMINATION': 'Eviction and termination', 'NOTICE_UNSPECIFIED': 'Notice (type not stated)', 'RENT_INCREASE_FEES': 'Rent increases, fees, charges',
    'RENT_PAYMENT_DISPUTE': 'Rent payment disputes', 'UTILITY_BILLING': 'Utility billing (RUBS, third-party)', 'DEPOSIT_RETURN': 'Deposits and refunds',
    'LOCKOUT_SELF_HELP': 'Lockouts and self-help', 'RETALIATION_HARASSMENT': 'Retaliation and harassment', 'DISCRIMINATION': 'Discrimination / fair housing',
    'ENTRY_PRIVACY': 'Landlord entry and privacy', 'RELOCATION_DISPLACEMENT': 'Relocation and displacement', 'LEASE_TERMS': 'Lease terms, renewal, roommates',
    'REGISTRATION_PAPERWORK': 'Rental registration paperwork', 'NOISE_NUISANCE': 'Noise', 'CONSTRUCTION_PERMIT': 'Construction / permits',
    'PUBLIC_SPACE': 'Public space (weeds, sidewalks, parking)', 'NEIGHBOR_BEHAVIOR': 'Neighbor behavior (drugs, violence)', 'ZONING_USE': 'Zoning / illegal unit / land use',
    'NOTICE_3DAY': '3-day notice', 'JCEO_CASE': 'Just cause eviction (JCEO)',
}
CAT_KEYS = sorted(CAT_GROUP, key=lambda k: (GIDX[CAT_GROUP[k]], CAT_LABEL[k]))
CAT_IDX = {k: i for i, k in enumerate(CAT_KEYS)}
# "3-day notice": the description says 3-day / three-day notice (or a 3-day pay / comply / vacate wording). 'for 3 days' is not matched.
THREE_DAY = re.compile(r"\b(?:3|three)\s*-?\s*days?'?s?\s*(?:written\s+)?(?:notices?|notif\w*)\b"
                       r"|\b(?:3|three)\s*-?\s*days?\s+(?:to\s+)?(?:pay|comply|vacate|quit|eviction|termination|cure|move|leave)\b", re.I)
JUST_CAUSE = re.compile(r"\bjust[\s-]*cause(?:\s+evict\w*)?(?:\s+ordinance)?", re.I)
LABELS = ['POTA', 'HOUSING', 'RRIO', 'JCEO', 'TRAO', 'PAOTHR', 'INRENT', 'RENTAG', 'HBMC']     # city labels offered as a filter
# A label counts when it stands alone OR is stuck to the next word ("JCEOTENANT RECEIVED..."): the export dropped some line breaks.
LABEL_RX = {l: re.compile(r'(?<![A-Za-z])' + l + r'(?![a-z])') for l in LABELS}


def clean(t):
    """same normalisation the vocabulary audit uses on DESCRIPTION"""
    t = (t or '').replace('\xa0', ' ').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
    t = t.replace('\u2019', "'").replace('\u2018', "'").replace('\u201c', '"').replace('\u201d', '"').replace('\u2013', '-').replace('\u2014', '-')
    return re.sub(r'\s+', ' ', t).strip()
STATUS_ORDER = ['COMPLETED', 'CLOSED', 'UNDER INVESTIGATION', 'OPEN DUPLICATE', 'INITIATED']
STATUS_LABEL = {'COMPLETED': 'Completed', 'CLOSED': 'Closed', 'UNDER INVESTIGATION': 'Under investigation', 'OPEN DUPLICATE': 'Open duplicate', 'INITIATED': 'Initiated'}
UNAS_REASON = {'INQUIRY_ONLY': 1, 'STAFF_NOTE_ONLY': 2, 'NO_ISSUE_WORDS': 3, 'UNCONFIRMED': 4}
UNAS_TEXT = ['', 'information request, no problem stated', 'staff note or city label only', 'no problem wording the rules recognise',
             'only borderline wording or a city label (not counted)', 'no description text']
# water bodies named on the map (positions checked: no residential property within 270 m of any of them)
WATER = [('Lake Union', 47.6385, -122.3355), ('Green Lake', 47.6800, -122.3405), ('Elliott Bay', 47.5950, -122.3700),
         ('Puget Sound', 47.5900, -122.4320), ('Lake Washington', 47.5900, -122.2580), ('Shilshole Bay', 47.6850, -122.4100)]
COARSE = 4e-4      # citywide gray base dots (degrees)
FINE = 1e-4        # fine gray base dots, only around the page's own district


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 20), b''):
            h.update(ch)
    return h.hexdigest()


def load_audit():
    out = {}
    with open(AUDIT_CSV, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            out[r['record_id']] = dict(cats=[c for c in (r['categories_text_evidence'] or '').split(';') if c], lane=r['lane'], desc=r['description'],
                                       labels=[x.strip() for x in (r['city_labels_in_description1'] or '').split(',') if x.strip()])
    return out


def load_match_words():
    """record id -> {category: [(phrase, context), ...]} from the audit's ACCEPTED matches only (the ones that colour a dot)."""
    out = defaultdict(lambda: defaultdict(list))
    with open(MATCH_CSV, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r['decision'] != 'ACCEPT': continue
            lst = out[r['record_id']][r['category']]
            item = (r['matched_phrase'], r['context'])
            if item not in lst and len(lst) < 3: lst.append(item)
    return out


CSV_GROUP_PREFIX = {'H': 'Housing map: ', 'P': 'Paperwork map: ', 'O': 'Both maps: ', 'U': 'Both maps: '}
CSV_COLUMNS = (['record_number', 'city_record_link', 'opened_date', 'year_opened', 'status', 'address', 'inspection_date_in_record', 'drawn_on_map']
               + [CSV_GROUP_PREFIX[g[3]] + g[1] for g in GROUPS]
               + ['problem_types_named', 'words_behind_problem_types', 'three_day_notice_words', 'jceo_basis', 'city_labels_in_staff_note', 'why_unassigned',
                  'city_building_outline_id', 'building_match'])
BLD_MATCH_TEXT = {'in': 'point inside the building outline', 'near': 'point within %d m of the building outline' % BLD_NEAR_M}


def csv_safe(t):
    """stop spreadsheet programs from running text that starts with = + - @ as a formula"""
    t = str(t)
    return "'" + t if t[:1] in ('=', '+', '-', '@') else t


def write_district_csv(path, rows, match_words):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(CSV_COLUMNS)
        for x in rows:
            words = []
            for c in x['catk']:
                for ph, cx in match_words.get(x['id'], {}).get(c, []):
                    words.append('%s: "%s" in "%s"' % (CAT_LABEL[c], ph, cx))
            w.writerow([x['id'], LINK_BASE + x['id'], x['od'], x['yr'] or '', STATUS_LABEL.get(STATUS_ORDER[x['st']], '') if x['st'] >= 0 else '', csv_safe(x['addr']),
                        'yes' if x['inn'] else 'no', 'yes' if x['la'] is not None else 'no']
                       + ['yes' if x['gm'] >> i & 1 else '' for i in range(len(GROUPS))]
                       + [csv_safe('; '.join(CAT_LABEL[c] for c in x['catk'])), csv_safe(' | '.join(words)), csv_safe(x['p3']), csv_safe(x['jc']),
                          '; '.join(LABELS[i] for i in range(len(LABELS)) if x['lb'] >> i & 1), UNAS_TEXT[x['ur']] if x['ur'] else '',
                          x['bid'] if x['bid'] else '', BLD_MATCH_TEXT.get(x['bm'], 'no building outline within %d m' % BLD_NEAR_M if x['la'] is not None and x['bm'] == '' and BLD_ON else '')])


def load_units():
    lat, lon, cra = [], [], []
    with open(UNITS_CSV, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            try:
                la = float(r['Latitude (centroid)']); lo = float(r['Longitude (centroid)'])
            except Exception:
                continue
            if la == 0 or lo == 0:
                continue
            lat.append(la); lon.append(lo); cra.append((r['Community Reporting Area'] or '').strip())
    return lat, lon, cra


def to_float(v):
    try:
        x = float(v)
        return x if x != 0 else None
    except Exception:
        return None


def id_num(rid):
    m = re.fullmatch(r'(\d{6})-(\d{2})CP', rid)
    if not m: raise ValueError('unexpected complaint id ' + rid)
    return int(m.group(1)) * 100 + int(m.group(2))


def _rdp(pts, eps):
    """Douglas-Peucker (iterative) on a list of (x, y) integer points; keeps both ends."""
    n = len(pts)
    if n < 3: return pts
    keep = [False] * n; keep[0] = keep[-1] = True; stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop(); ax, ay = pts[a]; bx, by = pts[b]; dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy); best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = math.hypot(px - ax, py - ay) if L == 0 else abs(dy * (px - ax) - dx * (py - ay)) / L
            if d > best: best, bi = d, i
        if best > eps: keep[bi] = True; stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def load_districts(eps=2):
    """District outlines -> {district: [polygon -> [ring -> flat delta-coded ints]]}, coordinates in 1e-5 degree units from (LON0, LAT0).
    Each ring: x0, y0, then (dx, dy) pairs. Simplified to about 2 m (eps = 2 units)."""
    g = json.load(open(GEO_PATH, encoding='utf-8'))
    out = {}
    for f in g['features']:
        d = int(f['properties']['C_DISTRICT']); geo = f['geometry']
        polys = geo['coordinates'] if geo['type'] == 'MultiPolygon' else [geo['coordinates']]
        enc = []
        for poly in polys:
            rings = []
            for ring in poly:
                q = []
                for x, y in ring:
                    pt = (int(round((x - LON0) * 1e5)), int(round((y - LAT0) * 1e5)))
                    if not q or q[-1] != pt: q.append(pt)
                q = _rdp(q, eps)
                if len(q) < 4: continue
                flat = [q[0][0], q[0][1]]
                for (x0, y0), (x1, y1) in zip(q, q[1:]): flat += [x1 - x0, y1 - y0]
                rings.append(flat)
            if rings: enc.append(rings)
        out[d] = enc
    return out


BLD_ON = False      # set by build() when the building outline file is present


def load_buildings():
    """City building outlines -> (outlines, grid, metadata). outlines[i] = (outline id, rings of (lon, lat), bbox, bbox area); grid: cell -> [i]."""
    if not os.path.exists(BLD_PATH): return [], {}, {}
    g = json.load(open(BLD_PATH, encoding='utf-8'))
    out, grid = [], defaultdict(list)
    for f in g['features']:
        geo = f.get('geometry')
        if not geo or geo['type'] not in ('Polygon', 'MultiPolygon'): continue
        polys = geo['coordinates'] if geo['type'] == 'MultiPolygon' else [geo['coordinates']]
        rings = [r for poly in polys for r in poly if len(r) >= 4]
        if not rings: continue
        xs = [p[0] for r in rings for p in r]; ys = [p[1] for r in rings for p in r]
        bb = (min(xs), max(xs), min(ys), max(ys)); pr = f.get('properties') or {}
        i = len(out); out.append((int(pr.get('OUTLINE_ID') or pr.get('OBJECTID') or 0), rings, bb, (bb[1] - bb[0]) * (bb[3] - bb[2])))
        for cx in range(int(math.floor(bb[0] / BLD_CELL)), int(math.floor(bb[1] / BLD_CELL)) + 1):
            for cy in range(int(math.floor(bb[2] / BLD_CELL)), int(math.floor(bb[3] / BLD_CELL)) + 1):
                grid[(cx, cy)].append(i)
    return out, grid, g.get('metadata', {})


def _inside(x, y, rings):
    """even-odd point-in-polygon over all rings (holes included)"""
    c = False
    for r in rings:
        n = len(r); j = n - 1
        for i in range(n):
            xi, yi = r[i]; xj, yj = r[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi: c = not c
            j = i
    return c


def match_building(la, lo, blds, grid):
    """(outline index, 'in' | 'near', meters) for a complaint point, or (-1, '', None) when no outline edge is within BLD_NEAR_M."""
    cx, cy = int(math.floor(lo / BLD_CELL)), int(math.floor(la / BLD_CELL))
    hits = [i for i in grid.get((cx, cy), []) if blds[i][2][0] <= lo <= blds[i][2][1] and blds[i][2][2] <= la <= blds[i][2][3] and _inside(lo, la, blds[i][1])]
    if hits: return min(hits, key=lambda i: (blds[i][3], i)), 'in', 0.0       # overlapping outlines: the smaller one
    mx, my = math.cos(math.radians(la)) * 111320.0, 110574.0
    best, bd = -1, float(BLD_NEAR_M)
    cand = sorted({i for ddx in (-1, 0, 1) for ddy in (-1, 0, 1) for i in grid.get((cx + ddx, cy + ddy), [])})
    for i in cand:
        bb = blds[i][2]
        if max(bb[0] - lo, 0, lo - bb[1]) * mx > bd or max(bb[2] - la, 0, la - bb[3]) * my > bd: continue
        for r in blds[i][1]:
            for (x1, y1), (x2, y2) in zip(r, r[1:]):
                ax, ay = (x1 - lo) * mx, (y1 - la) * my; bx, by = (x2 - lo) * mx, (y2 - la) * my
                dx, dy = bx - ax, by - ay; L2 = dx * dx + dy * dy
                t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
                d = math.hypot(ax + t * dx, ay + t * dy)
                if d < bd: best, bd = i, d
    return (best, 'near', bd) if best >= 0 else (-1, '', None)


def enc_building(rings):
    """rings -> flat delta-coded ints in 1e-6 degree units from (LON0, LAT0), simplified to about 0.2 m"""
    out = []
    for r in rings:
        q = []
        for x, y in r:
            pt = (int(round((x - LON0) * BLD_Q)), int(round((y - LAT0) * BLD_Q)))
            if not q or q[-1] != pt: q.append(pt)
        q = _rdp(q, 2)
        if len(q) < 4: continue
        flat = [q[0][0], q[0][1]]
        for (x0, y0), (x1, y1) in zip(q, q[1:]): flat += [x1 - x0, y1 - y0]
        out.append(flat)
    return out


def citywide_template(t):
    """The same page, worded for the whole city (no single highlighted district)."""
    def r(a, b):
        nonlocal t
        assert t.count(a) == 1, (t.count(a), a[:70]); t = t.replace(a, b)
    r('<title>District __N__ complaint maps | STLCA</title>', '<title>Citywide complaint maps | STLCA</title>')
    r('with Council District __N__ highlighted.', 'for every Seattle council district.')
    r('Maps &middot; Council District __N__', 'Maps &middot; All seven council districts')
    r('<h1>District __N__ complaint maps</h1>', '<h1>Citywide complaint maps</h1>')
    t = re.sub(r'<a class="ghost" href="district-__N__-[a-z]+\.html">District __N__ [a-z]+</a>', '', t)
    assert t.count('with District __N__ in full color') == 2
    t = t.replace('with District __N__ in full color', 'with every council district in full color')
    r('List the District __N__ records now on the maps', 'List the records now on the maps')
    r('<h2>District __N__ complaints by problem type</h2>', '<h2>Citywide complaints by problem type</h2>')
    r(' District __N__ has the dark outline.', '')
    r('<li><b>District __N__ is in full color; the rest of the city is faded context.</b> Click a faded dot to jump to that district&rsquo;s page for the details.</li>',
      '<li><b>Every council district is in full color.</b> Use the tabs at the top of the page to open one district&rsquo;s page.</li>')
    assert t.count('data-v="dist">District __N__</button>') == 2
    t = t.replace('data-v="dist">District __N__</button>', 'data-v="dist">Citywide</button>')    # hidden by the page script on the citywide page
    assert '__N__' not in t.replace('__N__.csv', ''), re.findall(r'.{40}__N__.{20}', t)[:3]
    return t


def build():
    data = json.load(open(JSON_PATH, encoding='utf-8-sig'))
    comps = [r for r in data if str(r.get('RECORDTYPE', '')).upper() == 'COMPLAINT']
    audit = load_audit()
    ulat, ulon, ucra = load_units()
    sha = sha256_file(JSON_PATH)
    districts = load_districts()
    global BLD_ON
    blds, bgrid, bmeta = load_buildings(); BLD_ON = bool(blds)
    day0 = date(2000, 1, 1)

    # ---- neighbourhood labels (median position of the residential properties in each reporting area)
    byc = defaultdict(list)
    for a, b, c in zip(ulat, ulon, ucra):
        if c: byc[c].append((a, b))
    labels = [dict(n=nm, la=round(sorted(x[0] for x in v)[len(v) // 2], 5), lo=round(sorted(x[1] for x in v)[len(v) // 2], 5), w=len(v)) for nm, v in byc.items()]
    # ---- gray base dots
    coarse = sorted({(int(round((a - LAT0) / COARSE)), int(round((b - LON0) / COARSE))) for a, b in zip(ulat, ulon)})
    fine = sorted({(int(round((a - LAT0) / FINE)), int(round((b - LON0) / FINE))) for a, b in zip(ulat, ulon)})
    city = [min(ulon), max(ulon), min(ulat), max(ulat)]
    pad_x, pad_y = (city[1] - city[0]) * 0.03, (city[3] - city[2]) * 0.03
    city = [round(city[0] - pad_x, 5), round(city[1] + pad_x, 5), round(city[2] - pad_y, 5), round(city[3] + pad_y, 5)]

    # ---- every complaint with coordinates
    recs = []; allrecs = []; total = Counter(); nocoord = Counter(); match_words = load_match_words(); bcache = {}
    for r in comps:
        d = r.get('DISTRICT')
        try: d = int(d)
        except Exception: d = 0
        if d not in range(1, 8): d = 0
        total[d] += 1
        la, lo = to_float(r.get('LATITUDE')), to_float(r.get('LONGITUDE'))
        if la is None or lo is None:
            la = lo = None; nocoord[d] += 1
        rid = r['RECORDNUM']; a = audit.get(rid)
        cats = [c for c in a['cats'] if c in CAT_GROUP] if a else []
        D0, D1 = clean(r.get('DESCRIPTION')), clean(r.get('DESCRIPTION1'))
        m3a, m3b = THREE_DAY.search(D0), THREE_DAY.search(D1)           # 3-day notice: DESCRIPTION and/or the City staff note in DESCRIPTION1
        m3 = bool(m3a or m3b)
        jl1, jl0 = bool(LABEL_RX['JCEO'].search(D1)), bool(LABEL_RX['JCEO'].search(D0))
        jw0, jw1 = JUST_CAUSE.search(D0), JUST_CAUSE.search(D1)
        jc = bool(jl1 or jl0 or jw0 or jw1)
        if m3: cats = [c for c in cats if c != 'NOTICE_UNSPECIFIED']    # a 3-day notice is shown as its own group, not also as "type not stated"
        gm = 0
        for c in cats:
            gm |= 1 << GIDX[CAT_GROUP[c]]
        if m3:
            gm |= 1 << GIDX['P3DAY']; cats = cats + ['NOTICE_3DAY']
        if jc:
            gm |= 1 << GIDX['PJCEO']; cats = cats + ['JCEO_CASE']
        ur = 0
        if gm == 0:
            gm = 1 << GIDX['UNAS']
            ur = 5 if a is None else UNAS_REASON.get(a['lane'], 3)
        lb = 0
        for li, lname in enumerate(LABELS):
            if LABEL_RX[lname].search(D1): lb |= 1 << li
        od = str(r.get('OPENDATE') or '')[:10]
        try: dt = (date.fromisoformat(od) - day0).days
        except Exception: dt = -1
        yr = int(r['OPENYEAR']) if r.get('OPENYEAR') else (int(od[:4]) if od[:4].isdigit() else 0)
        stt = str(r.get('STATUSCURRENT') or '').strip().upper()
        rec = (dict(id=rid, idn=id_num(rid), d=d, la=la, lo=lo, catk=list(cats), yr=yr, dt=dt, od=od, st=STATUS_ORDER.index(stt) if stt in STATUS_ORDER else -1,
                         inn=0 if str(r.get('NOINSPDATE T/F')) == 'True' else 1, gm=gm, ct=sorted(CAT_IDX[c] for c in cats), ur=ur, lb=lb,
                         addr=(r.get('ORIGINALADDRESS1') or '').strip().upper(),
                         p3=' and '.join(x for x in ([('the description says \u201c%s\u201d' % ' '.join(m3a.group(0).split()))] if m3a else []) + ([('the City staff note (DESCRIPTION1) says \u201c%s\u201d' % ' '.join(m3b.group(0).split()))] if m3b else [])),
                         jc=' and '.join(x for x in (["the City's JCEO label in DESCRIPTION1"] if jl1 else []) + (['JCEO typed in the description'] if jl0 else [])
                                         + ([('the description says \u201c%s\u201d' % ' '.join(jw0.group(0).split()))] if jw0 else []) + ([('the City staff note says \u201c%s\u201d' % ' '.join(jw1.group(0).split()))] if jw1 else []))))
        rec['bi'], rec['bm'], rec['bid'] = -1, '', 0
        if la is not None and blds:
            key = (la, lo)
            if key not in bcache: bcache[key] = match_building(la, lo, blds, bgrid)
            bi, bm, _ = bcache[key]
            if bi >= 0: rec['bi'], rec['bm'], rec['bid'] = bi, bm, blds[bi][0]
        allrecs.append(rec)
        if la is not None: recs.append(rec)
    yrs = [x['yr'] for x in recs if x['yr']]
    ymin, ymax = min(yrs), max(yrs)

    built = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    site_css = open(os.path.join(HERE, 'site_base.css'), encoding='utf-8').read()
    header = open(os.path.join(HERE, 'site_header.html'), encoding='utf-8').read()
    footer = open(os.path.join(HERE, 'site_footer.html'), encoding='utf-8').read()
    template = open(os.path.join(HERE, 'district_map_template.html'), encoding='utf-8').read()
    tabs = lambda n: ('<a href="citywide-map.html"%s>Citywide</a>' % (' class="on" aria-current="page"' if n == 0 else '')
                      + ''.join('<a href="district-%d-map.html"%s>District %d</a>' % (k, ' class="on" aria-current="page"' if k == n else '', k) for k in range(1, 8)))
    H_BITS = [i for i, g in enumerate(GROUPS) if g[3] == 'H']; P_BITS = [i for i, g in enumerate(GROUPS) if g[3] == 'P']
    anybit = lambda gm, bits: any(gm >> b & 1 for b in bits)

    for n in range(0, 8):          # n = 0 is the citywide page: every complaint with coordinates in full detail, no faded 'rest of the city'
        cur = sorted([x for x in recs if n == 0 or x['d'] == n], key=lambda x: (x['od'], x['id']))
        oth = [] if n == 0 else sorted([x for x in recs if x['d'] != n], key=lambda x: (x['d'], x['id']))
        n_total = sum(total.values()) if n == 0 else total[n]; n_nocoord = sum(nocoord.values()) if n == 0 else nocoord[n]
        addr_idx = {}; addrs = []
        for x in cur:
            if x['addr'] not in addr_idx: addr_idx[x['addr']] = len(addrs); addrs.append(x['addr'])
        gcount = Counter(); ureasons = Counter(); lcount = Counter(); scount = Counter()
        for x in cur:
            for gi in range(len(GROUPS)):
                if x['gm'] >> gi & 1: gcount[GROUPS[gi][0]] += 1
            if x['ur']: ureasons[x['ur']] += 1
            for li in range(len(LABELS)):
                if x['lb'] >> li & 1: lcount[li] += 1
            scount[x['st']] += 1
        las = sorted(x['la'] for x in cur); los = sorted(x['lo'] for x in cur)
        pc = lambda arr, p: arr[min(len(arr) - 1, max(0, int(round(p * (len(arr) - 1)))))]
        dbox = [round(pc(los, .004), 5), round(pc(los, .996), 5), round(pc(las, .004), 5), round(pc(las, .996), 5)]
        padlat, padlon = 0.02, 0.03
        fb = [(a, b) for a, b in fine if dbox[2] - padlat <= LAT0 + a * FINE <= dbox[3] + padlat and dbox[0] - padlon <= LON0 + b * FINE <= dbox[1] + padlon]
        fbox = [round(dbox[0] - padlon, 5), round(dbox[1] + padlon, 5), round(dbox[2] - padlat, 5), round(dbox[3] + padlat, 5)]
        bused = sorted({x['bi'] for x in cur if x['bi'] >= 0}); bloc = {b: i for i, b in enumerate(bused)}
        p3map = {i: x['p3'] for i, x in enumerate(cur) if x['p3']}
        jcmap = {i: x['jc'] for i, x in enumerate(cur) if x['jc']}
        payload = dict(
            district=n, q=dict(lat0=LAT0, lon0=LON0, coarse=COARSE, fine=FINE),
            totals=dict(complaints=n_total, plotted=len(cur), nocoord=n_nocoord, yearMin=ymin, yearMax=ymax, others=len(oth), noDistrict=total[0], noDistrictPlotted=sum(1 for x in (cur if n == 0 else oth) if x['d'] == 0),
                        housing=sum(1 for x in cur if anybit(x['gm'], H_BITS)), paper=sum(1 for x in cur if anybit(x['gm'], P_BITS)),
                        unassigned=gcount['UNAS'], threeDay=gcount['P3DAY'], jceo=gcount['PJCEO'],
                        bldIn=sum(1 for x in cur if x['bm'] == 'in'), bldNear=sum(1 for x in cur if x['bm'] == 'near'), bldNone=sum(1 for x in cur if x['bi'] < 0)),
            groups=[dict(k=k, label=lab, color=col, lane=ln, n=gcount[k]) for k, lab, col, ln in GROUPS],
            cats=[CAT_LABEL[k] for k in CAT_KEYS], catg=[GIDX[CAT_GROUP[k]] for k in CAT_KEYS],
            statuses=[STATUS_LABEL[s] for s in STATUS_ORDER], statusCounts=[scount[k] for k in range(len(STATUS_ORDER))],
            labelNames=LABELS, labelCounts=[lcount[i] for i in range(len(LABELS))],
            unasText=UNAS_TEXT, unasCounts=[ureasons[k] for k in range(6)],
            addrs=addrs, linkBase=LINK_BASE,
            pts=dict(la=[int(round((x['la'] - LAT0) * 1e5)) for x in cur], lo=[int(round((x['lo'] - LON0) * 1e5)) for x in cur], yr=[x['yr'] for x in cur],
                     dt=[x['dt'] for x in cur], st=[x['st'] for x in cur], inn=[x['inn'] for x in cur], gm=[x['gm'] for x in cur], ct=[x['ct'] for x in cur],
                     id=[x['idn'] for x in cur], ad=[addr_idx[x['addr']] for x in cur], ur=[x['ur'] for x in cur], lb=[x['lb'] for x in cur],
                     b=[bloc.get(x['bi'], -1) for x in cur],
                     **({'d': [x['d'] for x in cur]} if n == 0 else {})),
            p3=p3map, jc=jcmap,
            ot=dict(la=[int(round((x['la'] - LAT0) * 1e5)) for x in oth], lo=[int(round((x['lo'] - LON0) * 1e5)) for x in oth], yr=[x['yr'] - 2000 for x in oth],
                    st=[x['st'] for x in oth], inn=[x['inn'] for x in oth], gm=[x['gm'] for x in oth], d=[x['d'] for x in oth], id=[x['idn'] for x in oth], lb=[x['lb'] for x in oth]),
            baseC=dict(la=[a for a, _ in coarse], lo=[b for _, b in coarse]),
            baseF=dict(la=[a for a, _ in fb], lo=[b for _, b in fb], box=fbox),
            outlines=[dict(d=k, p=districts[k]) for k in sorted(districts)],
            labels=labels, water=[dict(n=nm, la=a, lo=b) for nm, a, b in WATER],
            view=dict(city=city, district=dbox, lat0=round((city[2] + city[3]) / 2, 5)),
            build=dict(built=built, source=os.path.basename(JSON_PATH), sha=sha[:12], audit=AUDIT_NAME),
            bl=dict(p=[enc_building(blds[b][1]) for b in bused], id=[blds[b][0] for b in bused], q=BLD_Q, near=BLD_NEAR_M,
                    name=BLD_NAME, downloaded=bmeta.get('downloaded', '')[:10]),
        )
        csv_name = 'citywide-map-records.csv' if n == 0 else 'district-%d-map-records.csv' % n
        csv_rows = sorted([x for x in allrecs if n == 0 or x['d'] == n], key=lambda x: (x['od'], x['id']))
        write_district_csv(os.path.join(OUT_DIR, csv_name), csv_rows, match_words)
        payload['csv'] = dict(file=csv_name, rows=len(csv_rows))
        js = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        tpl = template if n else citywide_template(template)
        html = (tpl.replace('/*__SITE_CSS__*/', site_css).replace('<!--SITE_HEADER-->', header).replace('<!--SITE_FOOTER-->', footer)
                .replace('<!--DISTRICT_TABS-->', tabs(n)).replace('__N__', str(n)).replace('/*__DATA__*/null', js))
        path = os.path.join(OUT_DIR, 'citywide-map.html' if n == 0 else 'district-%d-map.html' % n)
        with open(path, 'w', encoding='utf-8') as f: f.write(html)
        print('%s: %d complaints (%d drawn, %d without coordinates) + %d elsewhere in the city | 3-day notices %d | JCEO %d | %d fine + %d coarse base dots | %d buildings (%d in, %d near, %d none) -> %s (%d KB)'
              % ('district %d' % n if n else 'citywide', n_total, len(cur), n_nocoord, len(oth), gcount['P3DAY'], gcount['PJCEO'], len(fb), len(coarse),
                 len(bused), payload['totals']['bldIn'], payload['totals']['bldNear'], payload['totals']['bldNone'], os.path.basename(path), len(html) // 1024))


if __name__ == '__main__':
    if len(sys.argv) > 1: OUT_DIR = os.path.abspath(sys.argv[1])
    build()
