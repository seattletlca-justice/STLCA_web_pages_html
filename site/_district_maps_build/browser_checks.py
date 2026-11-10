"""browser_checks.py - scripted in-browser self-check of the seven pages (headless Chrome).
READS:  district-N-map.html in the site folder.
WRITES: _test_N.html, _out_N.txt and _results.json, only in %TEMP%/stlca_map_checks. Nothing in the site folder or any run folder is touched.
Run:  python browser_checks.py   (about 40 seconds; one line per district, "all checks pass" when fine)"""
import sys, os, re, json, html, subprocess, tempfile
SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pages')     # the folder holding the seven pages
SP = os.path.join(tempfile.gettempdir(), 'stlca_map_checks'); os.makedirs(SP, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HOOK = r"""
(function(){ var R = {}; try {
  var txt = function(h){ var d = document.createElement('div'); d.innerHTML = h; return d.textContent.replace(/\s+/g, ' ').trim(); };
  var gi = function(k){ return D.groups.findIndex(function(g){ return g.k === k; }); };
  R.counts = { Nc: Nc, No: No, plotted: D.totals.plotted, others: D.totals.others, jceoTotal: D.totals.jceo, threeDayTotal: D.totals.threeDay };
  R.start = { fcount: $('#fcount').textContent, passC: passC, passO: passO };
  // JCEO group: stored count, manual count from the bitmasks, and the bar/legend text
  var gj = gi('PJCEO'), g3 = gi('P3DAY'), manualJ = 0, manual3 = 0;
  for (var i = 0; i < Nc; i++){ if (CP.gm[i] >> gj & 1) manualJ++; if (CP.gm[i] >> g3 & 1) manual3++; }
  R.jceo = { n: D.groups[gj].n, manual: manualJ, total: D.totals.jceo, lane: D.groups[gj].lane, color: D.groups[gj].color, name: D.groups[gj].label };
  R.threeDay = { n: D.groups[g3].n, manual: manual3, total: D.totals.threeDay };
  // cards: one with JCEO + 3-day, one with JCEO only, one with 3-day only
  var kBoth = -1, kJ = -1, k3 = -1;
  for (var q = 0; q < Nc; q++){ var a = !!D.p3[String(q)], b = !!D.jc[String(q)]; if (a && b && kBoth < 0) kBoth = q; if (b && !a && kJ < 0) kJ = q; if (a && !b && k3 < 0) k3 = q; }
  var show = function(k){ if (k < 0) return null; selectRec(k, PANES[1], false); return { id: idStr(k), card: txt(PANES[1].card.innerHTML).slice(0, 520) }; };
  R.cardBoth = show(kBoth); R.cardJ = show(kJ); R.card3 = show(k3);
  // JCEO off in the paperwork pane: nothing is coloured JCEO any more; on again restores it
  var onBefore = PANES[1].cur[gj].length; PANES[1].on[gj] = false; recomputeMasks(); applyFilters();
  R.jcOff = { before: onBefore, after: PANES[1].cur[gj].length }; PANES[1].on[gj] = true; recomputeMasks(); applyFilters(); R.jcOff.restored = PANES[1].cur[gj].length;
  // lane separation
  var bad = 0; for (var g = 0; g < NG; g++){ if (D.groups[g].lane === 'P' && (PANES[0].cur[g].length || PANES[0].oth[g].length)) bad++; if (D.groups[g].lane === 'H' && (PANES[1].cur[g].length || PANES[1].oth[g].length)) bad++; }
  R.laneLeak = bad;
  // city label filter: JCEO
  var jI = D.labelNames.indexOf('JCEO'); S.lb = String(jI); applyFilters(); R.jceoLabelFilter = { passC: passC, expected: D.labelCounts[jI] }; S.lb = ''; applyFilters();
  // legends
  R.legend0 = Array.prototype.map.call(PANES[0].lg.querySelectorAll('label'), function(x){ return x.textContent.replace(/\s+/g, ' ').trim(); });
  R.legend1 = Array.prototype.map.call(PANES[1].lg.querySelectorAll('label'), function(x){ return x.textContent.replace(/\s+/g, ' ').trim(); });
  // text blocks
  R.kpis = txt(document.querySelector('.sumrow').innerHTML).slice(0, 600);
  R.hash = (location.hash = '#rec=' + idStr(7), hashRec());
  R.rowOverflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  // filters drive the legend numbers, tiles, bars and the stack badges (expected values are recounted here straight from the stored bitmasks)
  var numOf = function(el){ return +el.textContent.replace(/,/g, ''); };
  R.legFull = true; PANES.forEach(function(P){ P.groups.forEach(function(k){ if (numOf(P.nEl[k]) !== D.groups[k].n) R.legFull = false; }); });
  var cnt = {}, best = -1, bi = 0, i2;
  for (i2 = 0; i2 < Nc; i2++){ var a2 = CP.ad[i2]; cnt[a2] = (cnt[a2] || 0) + 1; if (cnt[a2] > best){ best = cnt[a2]; bi = a2; } }
  var qtxt = D.addrs[bi]; S.q = qtxt; applyFilters();
  var expG = new Array(NG).fill(0), match = [];
  for (i2 = 0; i2 < Nc; i2++){ if (D.addrs[CP.ad[i2]].indexOf(qtxt) >= 0){ match.push(i2); for (var g3 = 0; g3 < NG; g3++) if ((CP.gm[i2] >> g3) & 1) expG[g3]++; } }
  R.filt = { q: qtxt, pass: passC, expectPass: match.length, legendOk: true, tileFirst: txt(document.querySelector('.sumrow').innerHTML).slice(0, 80) };
  PANES.forEach(function(P){ P.groups.forEach(function(k){ if (numOf(P.nEl[k]) !== expG[k]) R.filt.legendOk = false; }); });
  R.filt.barsOk = true; for (var pi2 = 0; pi2 < 2; pi2++){ var nums = Array.prototype.map.call(document.querySelectorAll('#bars' + pi2 + ' .num'), numOf), want = []; G.forEach(function(gx, k){ if (gx.lane === LANEOF[pi2]) want.push(expG[k]); }); if (pi2 === 1) G.forEach(function(gx, k){ if (gx.lane === 'O' || gx.lane === 'U') want.push(expG[k]); }); if (JSON.stringify(nums) !== JSON.stringify(want)) R.filt.barsOk = false; }
  R.filt.stacks = [];
  PANES.forEach(function(P){
    var kc = {}, mxs = 0; match.forEach(function(k){ if (P.vg[k] >= 0){ var key = CP.la[k] + '/' + CP.lo[k]; kc[key] = (kc[key] || 0) + 1; if (kc[key] > mxs) mxs = kc[key]; } });
    R.filt.stacks.push({ expected: mxs, shown: P.stacks.length ? P.stacks[0].n : 1 });
  });
  $('#reset').onclick(); R.afterReset = true; PANES.forEach(function(P){ P.groups.forEach(function(k){ if (numOf(P.nEl[k]) !== D.groups[k].n) R.afterReset = false; }); });
  R.afterResetPass = passC;
  document.title = 'TEST ' + JSON.stringify(R);
  } catch (e) { document.title = 'TESTERR ' + String(e && e.stack || e).slice(0, 400); }
})();
"""
MARK = 'var hr = hashRec();'
rows = []
for n in range(0, 8):          # 0 = the citywide page
    h = open(os.path.join(SITE, 'citywide-map.html' if n == 0 else 'district-%d-map.html' % n), encoding='utf-8').read()
    assert h.count(MARK) == 1
    p = os.path.join(SP, '_test_%d.html' % n)
    open(p, 'w', encoding='utf-8').write(h.replace(MARK, HOOK + MARK))
    outp = os.path.join(SP, '_out_%d.txt' % n)
    with open(outp, 'wb') as fo:
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--virtual-time-budget=20000', '--window-size=1400,1000', '--dump-dom', 'file:///' + p.replace('\\', '/')], stdout=fo, stderr=subprocess.DEVNULL, timeout=180)
    dom = open(outp, encoding='utf-8', errors='replace').read()
    m = re.search(r'<title>TEST (.*?)</title>', dom, re.S)
    if not m:
        e = re.search(r'<title>TESTERR (.*?)</title>', dom, re.S); print('district', n, 'ERROR', html.unescape(e.group(1))[:300] if e else 'NO RESULT'); rows.append((n, None)); continue
    R = json.loads(html.unescape(m.group(1))); rows.append((n, R))
    c = R['counts']; j = R['jceo']; t3 = R['threeDay']
    ok = []
    ok.append(('counts', c['Nc'] == c['plotted'] and c['No'] == c['others']))
    ok.append(('jceo n=manual=total', j['n'] == j['manual'] == j['total']))
    ok.append(('3day n=manual=total', t3['n'] == t3['manual'] == t3['total']))
    ok.append(('jceo card line', (R['cardJ'] is None) or ('Just cause eviction (JCEO):' in R['cardJ']['card'])))
    ok.append(('both card lines', (R['cardBoth'] is None) or ('3-day notice:' in R['cardBoth']['card'] and 'Just cause eviction (JCEO):' in R['cardBoth']['card'])))
    ok.append(('3day-only card has no JCEO line', (R['card3'] is None) or ('Just cause eviction' not in R['card3']['card'])))
    ok.append(('jceo off/on', R['jcOff']['after'] == 0 and R['jcOff']['restored'] == R['jcOff']['before']))
    ok.append(('lane leak', R['laneLeak'] == 0))
    ok.append(('JCEO label filter', R['jceoLabelFilter']['passC'] == R['jceoLabelFilter']['expected']))
    ok.append(('legend right has JCEO', any('Just cause eviction (JCEO)' in x for x in R['legend1'])))
    f = R['filt']
    ok.append(('legend numbers at start = totals', R['legFull']))
    ok.append(('address filter: complaints passing', f['pass'] == f['expectPass']))
    ok.append(('address filter: legend numbers follow', f['legendOk']))
    ok.append(('address filter: bars follow', f['barsOk']))
    ok.append(('stack badge counts per map', all(x['expected'] == x['shown'] for x in f['stacks'])))
    ok.append(('reset restores numbers', R['afterReset'] and R['afterResetPass'] == c['Nc']))
    ok.append(('no sideways scroll', R['rowOverflow'] <= 0))
    bad = [k for k, v in ok if not v]
    print('district', n, '| JCEO', j['n'], '| 3-day', t3['n'], '| right legend items', len(R['legend1']), '| left', len(R['legend0']), '| FAIL: ' + ', '.join(bad) if bad else '| all checks pass')
json.dump({str(n): R for n, R in rows}, open(os.path.join(SP, '_results.json'), 'w', encoding='utf-8'), indent=1)
