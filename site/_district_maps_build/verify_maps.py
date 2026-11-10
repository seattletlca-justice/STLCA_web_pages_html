"""verify_maps.py - independent check of the seven whole-city district pages (with the JCEO group) against the source JSON, the audit CSV and the units file.
The group mapping, the wording patterns and the label detection are re-typed here (the generator is not imported). Read-only: it reads the pages, the source JSON, the audit CSV and the units CSV, and writes nothing.
If the group list or the wording rules in build_district_maps.py change, change them here too (they are re-typed on purpose).
Run:  python verify_maps.py   (about 20 seconds; prints one line per district and ALL OK)"""
import json, re, csv, os, sys
from collections import Counter, defaultdict
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'source')       # source files live inside the website folder
SITE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'pages')                         # the folder holding the seven pages
data = json.load(open(os.path.join(SRC, 'LLT_APPROVED_THROUGH_20251231.json'), encoding='utf-8-sig'))
comps = [r for r in data if str(r.get('RECORDTYPE', '')).upper() == 'COMPLAINT']
aud = {}
with open(os.path.join(SRC, 'record_issues.csv'), encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f): aud[r['record_id']] = r
ORDER = ['FIRE', 'STRUCT', 'HEAT', 'WATER', 'PLUMB', 'ELEC', 'PEST', 'OTHERH', 'P3DAY', 'PJCEO', 'PEVICT', 'PRENT', 'PDEP', 'PNOTE', 'PLEASE', 'POTH', 'OTHER', 'UNAS']
GROUP_OF = {}
for grp, cats in {
    'FIRE': 'FIRE_SMOKE_CO_GAS', 'STRUCT': 'STRUCTURAL DOORS_WINDOWS_SECURITY', 'HEAT': 'HEAT HOT_WATER WATER_SERVICE UTILITY_SERVICE_LOSS HVAC_COOLING',
    'WATER': 'MOLD_MOISTURE LEAKS_WATER_INTRUSION', 'PLUMB': 'PLUMBING_SEWAGE', 'ELEC': 'ELECTRICAL', 'PEST': 'PESTS',
    'OTHERH': 'ELEVATOR_ACCESS SANITATION_ODOR HAZMAT_AIR APPLIANCES_FIXTURES OVERCROWDING HAB_UNSPECIFIED UNINHABITABLE_SEVERITY',
    'PEVICT': 'EVICTION_TERMINATION', 'PRENT': 'RENT_INCREASE_FEES', 'PDEP': 'DEPOSIT_RETURN', 'PNOTE': 'NOTICE_UNSPECIFIED', 'PLEASE': 'LEASE_TERMS',
    'POTH': 'RETALIATION_HARASSMENT ENTRY_PRIVACY RELOCATION_DISPLACEMENT LOCKOUT_SELF_HELP DISCRIMINATION REGISTRATION_PAPERWORK RENT_PAYMENT_DISPUTE UTILITY_BILLING',
    'OTHER': 'NOISE_NUISANCE CONSTRUCTION_PERMIT PUBLIC_SPACE NEIGHBOR_BEHAVIOR ZONING_USE'}.items():
    for c in cats.split(): GROUP_OF[c] = grp
H = set(ORDER[:8]); P = set(ORDER[8:16])
T3 = re.compile(r"\b(?:3|three)\s*-?\s*days?'?s?\s*(?:written\s+)?(?:notices?|notif\w*)\b|\b(?:3|three)\s*-?\s*days?\s+(?:to\s+)?(?:pay|comply|vacate|quit|eviction|termination|cure|move|leave)\b", re.I)
JW = re.compile(r"\bjust[\s-]*cause(?:\s+evict\w*)?(?:\s+ordinance)?", re.I)
LABELS = ['POTA', 'HOUSING', 'RRIO', 'JCEO', 'TRAO', 'PAOTHR', 'INRENT', 'RENTAG', 'HBMC']
LRX = {l: re.compile(r'(?<![A-Za-z])' + l + r'(?![a-z])') for l in LABELS}

def clean(t):
    t = (t or '').replace('\xa0', ' ').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
    t = t.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-')
    return re.sub(r'\s+', ' ', t).strip()
sq = lambda m: ' '.join(m.group(0).split())

def truth(r):
    rid = r['RECORDNUM']; a = aud.get(rid)
    cats = [c for c in a['categories_text_evidence'].split(';') if c and c in GROUP_OF] if a else []
    D0, D1 = clean(r.get('DESCRIPTION')), clean(r.get('DESCRIPTION1'))
    m3a, m3b = T3.search(D0), T3.search(D1)
    jl1, jl0 = bool(LRX['JCEO'].search(D1)), bool(LRX['JCEO'].search(D0))
    jw0, jw1 = JW.search(D0), JW.search(D1)
    groups = set()
    for c in cats:
        if c == 'NOTICE_UNSPECIFIED' and (m3a or m3b): continue
        groups.add(GROUP_OF[c])
    if m3a or m3b: groups.add('P3DAY')
    if jl1 or jl0 or jw0 or jw1: groups.add('PJCEO')
    ur = 0
    if not groups:
        groups.add('UNAS'); ur = 5 if a is None else {'INQUIRY_ONLY': 1, 'STAFF_NOTE_ONLY': 2, 'NO_ISSUE_WORDS': 3, 'UNCONFIRMED': 4}.get(a['lane'], 3)
    p3 = ' and '.join(([('the description says “%s”' % sq(m3a))] if m3a else []) + ([('the City staff note (DESCRIPTION1) says “%s”' % sq(m3b))] if m3b else []))
    jc = ' and '.join((["the City's JCEO label in DESCRIPTION1"] if jl1 else []) + (['JCEO typed in the description'] if jl0 else []) + ([('the description says “%s”' % sq(jw0))] if jw0 else []) + ([('the City staff note says “%s”' % sq(jw1))] if jw1 else []))
    d = r.get('DISTRICT'); d = int(d) if str(d) in '1234567' and d not in (None, '') else 0
    return dict(id=rid, d=d, groups=groups, labels={l for l in LABELS if LRX[l].search(D1)}, p3=p3, jc=jc, ur=ur)

def has_ll(r):
    try: return float(r['LATITUDE']) != 0 and float(r['LONGITUDE']) != 0
    except Exception: return False
plotted = {r['RECORDNUM']: r for r in comps if has_ll(r)}
T = {rid: truth(r) for rid, r in plotted.items()}
def idn(rid): return int(rid[:6]) * 100 + int(rid[7:9])
byidn = {idn(rid): rid for rid in plotted}
ul, uo, uc = [], [], []
with open(os.path.join(SRC, 'ALL_UNITS_GEO_CENTROID_-7156434836825490772.csv'), encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        try: la = float(r['Latitude (centroid)']); lo = float(r['Longitude (centroid)'])
        except Exception: continue
        if la and lo: ul.append(la); uo.append(lo); uc.append((r['Community Reporting Area'] or '').strip())
coarse_truth = {(round((a - 47.45) / 4e-4), round((b + 122.45) / 4e-4)) for a, b in zip(ul, uo)}
fine_all = {(round((a - 47.45) / 1e-4), round((b + 122.45) / 1e-4)) for a, b in zip(ul, uo)}
cra = defaultdict(list)
for a, b, c in zip(ul, uo, uc):
    if c: cra[c].append((a, b))
class Errs(list):
    def append(self, x):
        k = x[0] if isinstance(x, tuple) else x
        if not any((e[0] if isinstance(e, tuple) else e) == k for e in self): super().append(x)
allok = True
for n in range(1, 8):
    h = open(os.path.join(SITE, 'district-%d-map.html' % n), encoding='utf-8').read()
    D = json.loads(re.search(r'<script id="D" type="application/json">(.*?)</script>', h, re.S).group(1).replace('<\\/', '</'))
    errs = Errs(); C, O = D['pts'], D['ot']
    if [g['k'] for g in D['groups']] != ORDER: errs.append(('group order', [g['k'] for g in D['groups']]))
    ids_c = [byidn.get(x) for x in C['id']]; ids_o = [byidn.get(x) for x in O['id']]
    if None in ids_c or None in ids_o: errs.append('unknown id')
    if len(ids_c) + len(ids_o) != len(plotted) or (set(ids_c) | set(ids_o)) != set(plotted): errs.append(('coverage', len(ids_c), len(ids_o), len(plotted)))
    if any(T[r]['d'] != n for r in ids_c) or any(T[r]['d'] == n for r in ids_o): errs.append('district split')
    gcount = Counter(); hous = pap = 0; p3m = {}; jcm = {}; ureasons = Counter(); lcount = Counter()
    for k, rid in enumerate(ids_c):
        r = plotted[rid]; t = T[rid]
        if abs(47.45 + C['la'][k] / 1e5 - float(r['LATITUDE'])) > 6e-6 or abs(-122.45 + C['lo'][k] / 1e5 - float(r['LONGITUDE'])) > 6e-6: errs.append(('coord', rid))
        if C['yr'][k] != int(r['OPENYEAR']) or C['dt'][k] != (date.fromisoformat(r['OPENDATE'][:10]) - date(2000, 1, 1)).days: errs.append(('year/date', rid))
        if (D['statuses'][C['st'][k]].upper() if C['st'][k] >= 0 else '') != str(r.get('STATUSCURRENT')).upper(): errs.append(('status', rid))
        if C['inn'][k] != (0 if r['NOINSPDATE T/F'] is True else 1): errs.append(('insp', rid))
        if D['addrs'][C['ad'][k]] != (r.get('ORIGINALADDRESS1') or '').strip().upper(): errs.append(('addr', rid))
        if {ORDER[b] for b in range(18) if C['gm'][k] >> b & 1} != t['groups']: errs.append(('groups', rid))
        if {LABELS[b] for b in range(len(LABELS)) if C['lb'][k] >> b & 1} != t['labels']: errs.append(('labels', rid))
        if C['ur'][k] != t['ur']: errs.append(('reason', rid, C['ur'][k], t['ur']))
        card_groups = {ORDER[D['catg'][c]] for c in C['ct'][k]}
        if (card_groups - {'UNAS'}) - t['groups'] or (t['groups'] - {'UNAS'} - card_groups): errs.append(('card categories', rid, card_groups, t['groups']))
        for g in t['groups']: gcount[g] += 1
        if t['groups'] & H: hous += 1
        if t['groups'] & P: pap += 1
        if t['p3']: p3m[str(k)] = t['p3']
        if t['jc']: jcm[str(k)] = t['jc']
        if t['ur']: ureasons[t['ur']] += 1
        for b in range(len(LABELS)):
            if C['lb'][k] >> b & 1: lcount[b] += 1
    for k, rid in enumerate(ids_o):
        r = plotted[rid]; t = T[rid]
        if abs(47.45 + O['la'][k] / 1e5 - float(r['LATITUDE'])) > 6e-6 or abs(-122.45 + O['lo'][k] / 1e5 - float(r['LONGITUDE'])) > 6e-6: errs.append(('ocoord', rid))
        if 2000 + O['yr'][k] != int(r['OPENYEAR']) or O['d'][k] != t['d']: errs.append(('oyear/dist', rid))
        if (D['statuses'][O['st'][k]].upper() if O['st'][k] >= 0 else '') != str(r.get('STATUSCURRENT')).upper(): errs.append(('ostatus', rid))
        if O['inn'][k] != (0 if r['NOINSPDATE T/F'] is True else 1): errs.append(('oinsp', rid))
        if {ORDER[b] for b in range(18) if O['gm'][k] >> b & 1} != t['groups']: errs.append(('ogroups', rid))
        if {LABELS[b] for b in range(len(LABELS)) if O['lb'][k] >> b & 1} != t['labels']: errs.append(('olabels', rid))
    for gi, g in enumerate(D['groups']):
        if g['n'] != gcount[ORDER[gi]]: errs.append(('group count', g['k'], g['n'], gcount[ORDER[gi]]))
    tt = D['totals']
    if (tt['housing'], tt['paper'], tt['threeDay'], tt['jceo'], tt['unassigned']) != (hous, pap, gcount['P3DAY'], gcount['PJCEO'], gcount['UNAS']): errs.append(('totals', tt, hous, pap))
    if D['p3'] != p3m: errs.append(('p3 map', len(D['p3']), len(p3m)))
    if D['jc'] != jcm: errs.append(('jc map', len(D['jc']), len(jcm)))
    if D['unasCounts'][1:] != [ureasons[k] for k in range(1, 6)]: errs.append(('unassigned reasons', D['unasCounts'], dict(ureasons)))
    if D['labelCounts'] != [lcount[b] for b in range(len(LABELS))]: errs.append(('label counts', D['labelCounts'], [lcount[b] for b in range(len(LABELS))]))
    if tt['complaints'] != sum(1 for r in comps if str(r.get('DISTRICT')) == str(n)): errs.append('district total')
    cs = {(a, b) for a, b in zip(D['baseC']['la'], D['baseC']['lo'])}
    if cs != coarse_truth: errs.append(('coarse base', len(cs), len(coarse_truth)))
    fb = D['baseF']; box = fb['box']
    fine_truth = {(qa, qb) for qa, qb in fine_all if box[2] <= 47.45 + qa * 1e-4 <= box[3] and box[0] <= -122.45 + qb * 1e-4 <= box[1]}
    if {(a, b) for a, b in zip(fb['la'], fb['lo'])} != fine_truth: errs.append(('fine base', len(fb['la']), len(fine_truth)))
    want = {nm: (sorted(x[0] for x in v)[len(v) // 2], sorted(x[1] for x in v)[len(v) // 2], len(v)) for nm, v in cra.items()}
    got = {x['n']: (x['la'], x['lo'], x['w']) for x in D['labels']}
    if set(want) != set(got) or any(abs(want[k][0] - got[k][0]) > 6e-6 or abs(want[k][1] - got[k][1]) > 6e-6 or want[k][2] != got[k][2] for k in want): errs.append('neighbourhood labels')
    print('district', n, '| current', len(ids_c), '| others', len(ids_o), '| 3-day', gcount['P3DAY'], '| JCEO', gcount['PJCEO'], '| housing', hous, '| paper', pap, '| unassigned', gcount['UNAS'], '| OK' if not errs else errs[:4])
    allok &= not errs

# ---- the record CSVs and the district outlines (each checked against the page and the GeoJSON, not against the builder) ----
import csv as _csv
def _page_data(n):
    h = open(os.path.join(SITE, 'district-%d-map.html' % n), encoding='utf-8').read()
    return json.loads(re.search(r'<script id="D" type="application/json">(.*?)</script>', h, re.S).group(1))
_geo = json.load(open(os.path.join(HERE, 'source', 'seattle_council_districts_CURRENT.geojson'), encoding='utf-8'))
try:
    from shapely.geometry import shape as _shape, Polygon as _Poly
except Exception:
    _shape = None
for n in range(1, 8):
    errs = []; D = _page_data(n)
    rows = list(_csv.DictReader(open(os.path.join(SITE, D['csv']['file']), encoding='utf-8-sig', newline='')))
    ids = [r['record_number'] for r in rows]
    if len(rows) != D['totals']['complaints'] or D['csv']['rows'] != len(rows): errs.append(('csv rows', len(rows), D['totals']['complaints']))
    if len(set(ids)) != len(ids): errs.append('csv duplicate records')
    drawn = [r for r in rows if r['drawn_on_map'] == 'yes']
    if len(drawn) != D['totals']['plotted']: errs.append(('csv drawn', len(drawn), D['totals']['plotted']))
    pid = {'%06d-%02dCP' % (v // 100, v % 100) for v in D['pts']['id']}
    if {r['record_number'] for r in drawn} != pid: errs.append('csv drawn ids differ from page dots')
    cols = [c for c in rows[0].keys() if c.startswith(('Housing map: ', 'Paperwork map: ', 'Both maps: '))]
    if len(cols) != len(D['groups']): errs.append('csv group columns')
    for c, g in zip(cols, D['groups']):
        if not c.endswith(g['label']): errs.append(('csv column order', c, g['label']))
        k = sum(1 for r in drawn if r[c] == 'yes')
        if k != g['n']: errs.append(('csv group count', g['label'], k, g['n']))
    if sum(1 for r in rows if r['city_record_link'] != 'https://services.seattle.gov/portal/customize/LinkToRecord.aspx?altId=' + r['record_number']): errs.append('csv links')
    p3 = sum(1 for r in drawn if r['three_day_notice_words']); jc = sum(1 for r in drawn if r['jceo_basis'])
    if p3 != D['totals']['threeDay'] or jc != D['totals']['jceo']: errs.append(('csv 3-day/JCEO words', p3, jc))
    if _shape:
        for f in _geo['features']:
            d = f['properties']['C_DISTRICT']; orig = _shape(f['geometry'])
            o = [x for x in D['outlines'] if x['d'] == d][0]; polys = []
            for poly in o['p']:
                rs = []
                for fl in poly:
                    x, y = fl[0], fl[1]; pts = [(x, y)]
                    for q in range(1, len(fl) // 2): x += fl[2 * q]; y += fl[2 * q + 1]; pts.append((-122.45 + x / 1e5, 47.45 + y / 1e5)); 
                    pts[0] = (-122.45 + fl[0] / 1e5, 47.45 + fl[1] / 1e5); rs.append(pts)
                polys.append(_Poly(rs[0], rs[1:]))
            from shapely.ops import unary_union as _u
            got = _u([q.buffer(0) for q in polys])   # outlines are simplified to about 2 m; allow 0.2% of the district's area
            if orig.symmetric_difference(got.buffer(0)).area / orig.area > 0.002: errs.append(('outline differs from GeoJSON', d))
    else: errs.append('shapely missing: outline check skipped')
    print('district', n, '| csv rows', len(rows), '| drawn', len(drawn), '| group columns match legends | outlines match GeoJSON', '| OK' if not errs else errs[:4])
    allok &= not errs

# ---- the citywide page, checked against the seven district pages (sums of their counts and ids) ----
def _city_check():
    errs = []; C = json.loads(re.search(r'<script id="D" type="application/json">(.*?)</script>', open(os.path.join(SITE, 'citywide-map.html'), encoding='utf-8').read(), re.S).group(1))
    pages = [_page_data(n) for n in range(1, 8)]
    ids = set(); gsum = [0] * len(C['groups']); nodist = 0
    for D in pages:
        ids |= {v for v in D['pts']['id']}
        for i, g in enumerate(D['groups']): gsum[i] += g['n']
    O = pages[0]['ot']                                    # page 1's "rest of the city" holds every other district plus the no-district complaints
    for k in range(len(O['id'])):
        if O['d'][k] == 0:
            nodist += 1; ids.add(O['id'][k])
            for i in range(len(gsum)): gsum[i] += O['gm'][k] >> i & 1
    P = C['pts']
    if len(P['id']) != len(ids) or set(P['id']) != ids: errs.append(('citywide ids', len(P['id']), len(ids)))
    if len(set(P['id'])) != len(P['id']): errs.append('citywide duplicate ids')
    for i, g in enumerate(C['groups']):
        if g['n'] != gsum[i]: errs.append(('citywide group', g['label'], g['n'], gsum[i]))
    if C['totals']['complaints'] != sum(D['totals']['complaints'] for D in pages) + pages[0]['totals']['noDistrict']: errs.append('citywide complaint total')
    if C['totals']['nocoord'] != sum(D['totals']['nocoord'] for D in pages) + pages[0]['totals']['noDistrict'] - nodist: errs.append('citywide no-coordinate total')
    if len(C['ot']['id']) != 0: errs.append('citywide has faded dots')
    dd = Counter(P['d']); 
    for n, D in enumerate(pages, 1):
        if dd[n] != D['totals']['plotted']: errs.append(('citywide district count', n, dd[n], D['totals']['plotted']))
    if dd[0] != nodist: errs.append(('citywide no-district count', dd[0], nodist))
    rows = list(csv.DictReader(open(os.path.join(SITE, C['csv']['file']), encoding='utf-8-sig', newline='')))
    if len(rows) != C['totals']['complaints'] or len({r['record_number'] for r in rows}) != len(rows): errs.append(('citywide csv rows', len(rows)))
    drawn = [r for r in rows if r['drawn_on_map'] == 'yes']
    if {r['record_number'] for r in drawn} != {'%06d-%02dCP' % (v // 100, v % 100) for v in P['id']}: errs.append('citywide csv drawn ids')
    cols = [c for c in rows[0].keys() if c.startswith(('Housing map: ', 'Paperwork map: ', 'Both maps: '))]
    for c, g in zip(cols, C['groups']):
        if sum(1 for r in drawn if r[c] == 'yes') != g['n']: errs.append(('citywide csv group', g['label']))
    print('citywide | dots', len(P['id']), '| csv rows', len(rows), '| groups = sum of the seven district pages (+', nodist, 'no-district)', '| OK' if not errs else errs[:4])
    return not errs
allok &= _city_check()
print('ALL OK' if allok else 'PROBLEMS FOUND')
