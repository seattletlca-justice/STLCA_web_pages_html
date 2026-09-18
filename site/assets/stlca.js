/* ==========================================================================
   STLCA shared behaviour: chrome, data binding, charts, search.
   Every figure rendered here comes from window.STLCA_DATA (assets/data.js),
   which build.py generates from data/*.json. Nothing is typed into markup.
   ========================================================================== */
(function () {
  "use strict";

  var D = window.STLCA_DATA;
  if (!D) { console.error("STLCA: data.js not loaded"); return; }

  // -------------------------------------------------------------- helpers
  var num = function (n) { return n == null ? "—" : n.toLocaleString("en-US"); };
  var pct = function (n) { return n == null ? "—" : n.toFixed(1) + "%"; };
  var esc = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var depth = function () {
    // how many directory levels deep this page sits, for relative links
    var p = location.pathname.split("/").filter(Boolean);
    var i = p.lastIndexOf("STLCA_SITE");
    return i === -1 ? (p.length > 1 ? p.length - 1 : 0) : p.length - i - 2;
  };
  var ROOT = new Array(depth() + 1).join("../");
  window.STLCA_ROOT = ROOT;

  // A missing field renders as a visible absence, never a zero (instructions 6.3)
  function field(v, fmt) {
    if (v === undefined || v === null) return '<span title="not present in the data layer">—</span>';
    return (fmt || num)(v);
  }
  window.stlcaField = field;

  // -------------------------------------------------------------- chrome
  var NAV = [
    ["The Record", "index.html"],
    ["Findings", "findings/index.html"],
    ["Districts", "districts/index.html"],
    ["Dashboards", "dashboards/index.html"],
    ["Case Studies", "case-studies/index.html"],
    ["Reports", "reports/index.html"],
    ["Methodology", "methodology.html"],
    ["About", "about.html"]
  ];

  function chrome() {
    var here = document.body.getAttribute("data-page") || "";
    var head = document.createElement("header");
    head.className = "site-head";
    head.innerHTML =
      '<div class="wrap">' +
      '<a class="brand" href="' + ROOT + 'index.html"><b>STLCA</b>' +
      '<span>Records → Review → Accountability</span></a>' +
      '<nav class="site-nav">' +
      NAV.map(function (n) {
        var cur = n[1] === here ? ' aria-current="page"' : "";
        return '<a href="' + ROOT + n[1] + '"' + cur + ">" + n[0] + "</a>";
      }).join("") +
      "</nav>" +
      '<label class="sr" for="q-top">Search this site</label>' +
      '<input id="q-top" class="site-search" type="search" placeholder="Search the record…">' +
      "</div>";
    document.body.insertBefore(head, document.body.firstChild);

    var u = D.findings.universe, s = D.findings.source;
    var foot = document.createElement("footer");
    foot.className = "site-foot";
    foot.innerHTML =
      '<div class="wrap">' +
      '<p class="tagline">Don’t take our word for it. Follow the record.</p>' +
      "<p>STLCA — Seattle Tenant-Landlord Compliance &amp; Accountability. " +
      "Powered by Seattle R.A.R.E., the Records Accountability &amp; Review Engine.<br>" +
      "STLCA is not an enforcement agency. It issues no orders, levies no fines, and makes no " +
      "legal findings of guilt or liability.</p>" +
      '<p class="prov"><b>Universe</b> ' + num(u.records) + " landlord-tenant candidate records through " +
      u.through + " (" + num(u.assigned_to_district) + " district-assigned, " + num(u.unassigned) +
      " unassigned)<br><b>Source</b> " + esc(s.file) + "<br><b>SHA-256</b> " + s.sha256 +
      "<br><b>Data layer built</b> " + D.generated + " · <b>Reconciliation</b> " +
      D.reconciliation.status + "</p>" +
      "</div>";
    document.body.appendChild(foot);

    var q = document.getElementById("q-top");
    q.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && q.value.trim())
        location.href = ROOT + "search.html?q=" + encodeURIComponent(q.value.trim());
    });
  }

  // -------------------------------------------------------------- tooltip
  var tip;
  function showTip(html, ev) {
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; document.body.appendChild(tip); }
    tip.innerHTML = html;
    tip.classList.add("on");
    var r = tip.getBoundingClientRect();
    var x = Math.min(ev.clientX + 14, innerWidth - r.width - 8);
    var y = Math.max(8, ev.clientY - r.height - 12);
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { if (tip) tip.classList.remove("on"); }

  // -------------------------------------------------------------- charts
  var SVGNS = "http://www.w3.org/2000/svg";
  function el(n, a) {
    var e = document.createElementNS(SVGNS, n);
    for (var k in a) if (a[k] != null) e.setAttribute(k, a[k]);
    return e;
  }
  function series_colors() {
    return document.body.classList.contains("screen")
      ? ["#2d7ff9", "#c17f00"] : ["#2d7ff9", "#f59e0b"];
  }

  function shell(host, o) {
    var fig = document.createElement("figure");
    fig.className = "chart";
    var h = "";
    if (o.title) h += '<div class="chart-title">' + esc(o.title) + "</div>";
    if (o.sub) h += '<div class="chart-sub">' + esc(o.sub) + "</div>";
    fig.innerHTML = h;
    host.appendChild(fig);
    return fig;
  }

  function legend(fig, names, colors) {
    if (names.length < 2) return;               // one series needs no legend box
    var d = document.createElement("div");
    d.className = "chart-legend";
    d.innerHTML = names.map(function (n, i) {
      return '<span><i style="background:' + colors[i] + '"></i>' + esc(n) + "</span>";
    }).join("");
    fig.appendChild(d);
  }

  function tableView(fig, cats, names, rows, fmt) {
    var wrap = document.createElement("div");
    wrap.className = "scroll-x";
    wrap.hidden = true;
    var t = "<table class='data'><thead><tr><th>" + esc(cats.label || "") + "</th>" +
      names.map(function (n) { return "<th>" + esc(n) + "</th>"; }).join("") + "</tr></thead><tbody>";
    cats.values.forEach(function (c, i) {
      t += "<tr><td>" + esc(c) + "</td>" +
        rows.map(function (r) { return "<td>" + (fmt ? fmt(r[i]) : num(r[i])) + "</td>"; }).join("") + "</tr>";
    });
    wrap.innerHTML = t + "</tbody></table>";
    var b = document.createElement("button");
    b.className = "tbl-toggle"; b.type = "button";
    b.textContent = "Show data table";
    b.setAttribute("aria-expanded", "false");
    b.addEventListener("click", function () {
      wrap.hidden = !wrap.hidden;
      b.textContent = wrap.hidden ? "Show data table" : "Hide data table";
      b.setAttribute("aria-expanded", String(!wrap.hidden));
    });
    fig.appendChild(b);
    fig.appendChild(wrap);
  }

  function caption(fig, text) {
    if (!text) return;
    var c = document.createElement("figcaption");
    c.innerHTML = text;
    fig.appendChild(c);
  }

  /* Vertical bars. o = {title, sub, cats, series:[{name,values}], fmt, caption,
     labelEvery, unit} -- 4px rounded data-ends, 2px gap, recessive grid. */
  function barChart(host, o) {
    var fig = shell(host, o), C = series_colors();
    var names = o.series.map(function (s) { return s.name; });
    legend(fig, names, C);

    var W = 900, H = o.height || 300, P = { t: 18, r: 12, b: 34, l: 52 };
    var iw = W - P.l - P.r, ih = H - P.t - P.b;
    var max = o.max || Math.max.apply(null, o.series.reduce(function (a, s) { return a.concat(s.values); }, [1]));
    var ticks = 4, band = iw / o.cats.length, ns = o.series.length;
    var bw = Math.max(2, (band - 8) / ns - (ns > 1 ? 2 : 0));   // 2px surface gap
    var y = function (v) { return P.t + ih - (v / max) * ih; };

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, class: "chart-svg",
      role: "img", "aria-label": o.title || "chart" });

    for (var i = 0; i <= ticks; i++) {
      var v = max * i / ticks, yy = y(v);
      svg.appendChild(el("line", { class: "gridline", x1: P.l, x2: W - P.r, y1: yy, y2: yy }));
      var tx = el("text", { class: "axis-txt", x: P.l - 8, y: yy + 4, "text-anchor": "end" });
      tx.textContent = o.fmt ? o.fmt(v) : num(Math.round(v));
      svg.appendChild(tx);
    }

    var every = o.labelEvery || Math.ceil(o.cats.length / 12);
    o.cats.forEach(function (c, ci) {
      var x0 = P.l + ci * band;
      o.series.forEach(function (s, si) {
        var v = s.values[ci];
        if (v == null) return;
        var bx = x0 + (band - (bw * ns + (ns - 1) * 2)) / 2 + si * (bw + 2);
        var bh = Math.max(1, (v / max) * ih);
        svg.appendChild(el("rect", { class: "mark", x: bx, y: y(v), width: bw, height: bh,
          rx: Math.min(4, bw / 2), fill: C[si] }));
      });
      if (ci % every === 0) {
        var lx = el("text", { class: "axis-txt", x: x0 + band / 2, y: H - 12, "text-anchor": "middle" });
        lx.textContent = c;
        svg.appendChild(lx);
      }
      // one hit target per category, wider than the marks
      var hit = el("rect", { class: "hit", x: x0, y: P.t, width: band, height: ih });
      hit.addEventListener("mousemove", function (ev) {
        showTip("<b>" + esc(o.catLabel ? o.catLabel + " " + c : c) + "</b>" +
          o.series.map(function (s, si) {
            return '<div class="r"><span><i style="background:' + C[si] + '"></i>' + esc(s.name) +
              "</span><span>" + (o.fmt ? o.fmt(s.values[ci]) : num(s.values[ci])) + "</span></div>";
          }).join(""), ev);
      });
      hit.addEventListener("mouseleave", hideTip);
      svg.appendChild(hit);
    });

    fig.appendChild(svg);
    tableView(fig, { label: o.catLabel || "", values: o.cats }, names,
      o.series.map(function (s) { return s.values; }), o.fmt);
    caption(fig, o.caption);
    return fig;
  }

  /* Horizontal bars -- for ranked categories with long names. */
  function barChartH(host, o) {
    var fig = shell(host, o), C = series_colors();
    var n = o.cats.length, rowH = o.rowH || 30;
    var W = 900, H = n * rowH + 16, P = { t: 6, r: 60, b: 6, l: o.labelW || 210 };
    var iw = W - P.l - P.r;
    var max = o.max || Math.max.apply(null, o.values.concat([1]));
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, class: "chart-svg",
      role: "img", "aria-label": o.title || "chart" });

    o.cats.forEach(function (c, i) {
      var v = o.values[i], yv = P.t + i * rowH, bh = rowH - 10;   // 2px+ surface gap
      var lw = Math.max(2, (v / max) * iw);
      var lab = el("text", { class: "axis-txt", x: P.l - 10, y: yv + bh / 2 + 4, "text-anchor": "end" });
      lab.textContent = c;
      svg.appendChild(lab);
      svg.appendChild(el("rect", { class: "mark", x: P.l, y: yv, width: lw, height: bh,
        rx: 4, fill: o.colors ? o.colors[i] : C[0] }));
      var val = el("text", { class: "val-txt", x: P.l + lw + 8, y: yv + bh / 2 + 4 });
      val.textContent = o.fmt ? o.fmt(v) : num(v);      // direct label (relief rule)
      svg.appendChild(val);
      var hit = el("rect", { class: "hit", x: 0, y: yv - 3, width: W, height: rowH });
      hit.addEventListener("mousemove", function (ev) {
        showTip("<b>" + esc(c) + "</b><div class='r'><span>" + esc(o.unit || "records") +
          "</span><span>" + (o.fmt ? o.fmt(v) : num(v)) + "</span></div>" +
          (o.notes && o.notes[i] ? "<div style='margin-top:4px;color:#aebbd0'>" + esc(o.notes[i]) + "</div>" : ""), ev);
      });
      hit.addEventListener("mouseleave", hideTip);
      svg.appendChild(hit);
    });

    fig.appendChild(svg);
    tableView(fig, { label: o.catLabel || "", values: o.cats }, [o.seriesName || o.unit || "Value"],
      [o.values], o.fmt);
    caption(fig, o.caption);
    return fig;
  }

  /* Line with crosshair. o = {cats, series:[{name,values}], fmt, ...} */
  function lineChart(host, o) {
    var fig = shell(host, o), C = series_colors();
    var names = o.series.map(function (s) { return s.name; });
    legend(fig, names, C);

    var W = 900, H = o.height || 300, P = { t: 18, r: 46, b: 34, l: 52 };
    var iw = W - P.l - P.r, ih = H - P.t - P.b;
    var max = o.max || Math.max.apply(null, o.series.reduce(function (a, s) { return a.concat(s.values); }, [1]));
    var n = o.cats.length;
    var x = function (i) { return P.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw); };
    var y = function (v) { return P.t + ih - (v / max) * ih; };

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, class: "chart-svg",
      role: "img", "aria-label": o.title || "chart" });
    for (var i = 0; i <= 4; i++) {
      var v = max * i / 4, yy = y(v);
      svg.appendChild(el("line", { class: "gridline", x1: P.l, x2: W - P.r, y1: yy, y2: yy }));
      var tx = el("text", { class: "axis-txt", x: P.l - 8, y: yy + 4, "text-anchor": "end" });
      tx.textContent = o.fmt ? o.fmt(v) : num(Math.round(v));
      svg.appendChild(tx);
    }
    var every = o.labelEvery || Math.ceil(n / 12);
    o.cats.forEach(function (c, i) {
      if (i % every) return;
      var t = el("text", { class: "axis-txt", x: x(i), y: H - 12, "text-anchor": "middle" });
      t.textContent = c; svg.appendChild(t);
    });

    if (o.bands) o.bands.forEach(function (b) {
      svg.appendChild(el("rect", { x: x(b.from), y: P.t, width: x(b.to) - x(b.from), height: ih,
        fill: document.body.classList.contains("screen") ? "#ffffff" : "#0a1628", opacity: .045 }));
    });

    o.series.forEach(function (s, si) {
      var d = s.values.map(function (v, i) { return (i ? "L" : "M") + x(i) + " " + y(v); }).join(" ");
      svg.appendChild(el("path", { class: "mark", d: d, fill: "none", stroke: C[si],
        "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      s.values.forEach(function (v, i) {
        svg.appendChild(el("circle", { class: "mark", cx: x(i), cy: y(v), r: 4, fill: C[si],
          stroke: document.body.classList.contains("screen") ? "#0a1628" : "#fff", "stroke-width": 2 }));
      });
      // selective direct label: last point only
      var lastV = s.values[n - 1];
      var lbl = el("text", { class: "val-txt", x: x(n - 1) + 9, y: y(lastV) + 4, fill: C[si] });
      lbl.textContent = o.fmt ? o.fmt(lastV) : num(lastV);
      svg.appendChild(lbl);
    });

    var cross = el("line", { class: "gridline", y1: P.t, y2: P.t + ih, opacity: 0, "stroke-width": 1 });
    svg.appendChild(cross);
    var hitW = iw / Math.max(1, n - 1);
    o.cats.forEach(function (c, i) {
      var hit = el("rect", { class: "hit", x: x(i) - hitW / 2, y: P.t, width: hitW, height: ih });
      hit.addEventListener("mousemove", function (ev) {
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", .5);
        showTip("<b>" + esc(o.catLabel ? o.catLabel + " " + c : c) + "</b>" +
          o.series.map(function (s, si) {
            return '<div class="r"><span><i style="background:' + C[si] + '"></i>' + esc(s.name) +
              "</span><span>" + (o.fmt ? o.fmt(s.values[i]) : num(s.values[i])) + "</span></div>";
          }).join(""), ev);
      });
      hit.addEventListener("mouseleave", function () { cross.setAttribute("opacity", 0); hideTip(); });
      svg.appendChild(hit);
    });

    fig.appendChild(svg);
    tableView(fig, { label: o.catLabel || "", values: o.cats }, names,
      o.series.map(function (s) { return s.values; }), o.fmt);
    caption(fig, o.caption);
    return fig;
  }

  // -------------------------------------------------------------- search
  function runSearch(q, kinds) {
    var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    return D.search.map(function (e) {
      var hay = (e.title + " " + e.text + " " + e.kind + " " + e.tags.join(" ")).toLowerCase();
      if (kinds && kinds.length && kinds.indexOf(e.kind) === -1) return null;
      if (!terms.length) return { e: e, score: 0 };
      var score = 0;
      for (var i = 0; i < terms.length; i++) {
        if (hay.indexOf(terms[i]) === -1) return null;
        score += e.title.toLowerCase().indexOf(terms[i]) !== -1 ? 3 : 1;
      }
      return { e: e, score: score };
    }).filter(Boolean).sort(function (a, b) { return b.score - a.score; });
  }

  function highlight(text, q) {
    var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    var out = esc(text.slice(0, 240));
    terms.forEach(function (t) {
      out = out.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return out;
  }

  // -------------------------------------------------------------- expose
  window.STLCA = {
    data: D, num: num, pct: pct, esc: esc, field: field, root: ROOT,
    barChart: barChart, barChartH: barChartH, lineChart: lineChart,
    search: runSearch, highlight: highlight, colors: series_colors
  };

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", chrome);
  else chrome();
})();
