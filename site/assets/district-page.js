/* ==========================================================================
   One district template, used by all seven district pages.
   The only thing that differs between district-1.html … district-7.html is
   <body data-district="N">. Every figure comes from District_N_SUMMARY.json
   via data.js — nothing about a district is expressed in markup.
   ========================================================================== */
(function () {
  "use strict";
  var S = window.STLCA, D = S.data;
  var id = document.body.getAttribute("data-district");
  var d = D.districts[id];
  if (!d) { document.querySelector("main").innerHTML = "<p>Unknown district.</p>"; return; }

  var f = D.findings, t = d.totals, ic = d.inspection_completeness;
  var comp = d.recordtypedesc_composition, sc = d.substantive_complaint_classification;
  var hc = d.habitability_categories, rt = d.resolution_time_days;

  document.title = "District " + id + " — " + d.name + " — STLCA";
  document.getElementById("crumb-d").textContent = "District " + id;
  document.getElementById("eyebrow").textContent = "District " + id + " · " + d.name;
  document.getElementById("title").textContent = "District " + id;
  document.getElementById("subtitle").textContent = d.name;

  document.getElementById("lede").textContent =
    S.num(t.record_count) + " landlord-tenant records across " + S.num(t.unique_addresses) +
    " distinct addresses. " + S.pct(ic.no_lastinspdate_pct) +
    " of them have no recorded inspection date. This district's figures use this district's own " +
    "record count as the denominator — they are not shares of the citywide total.";

  function tiles(host, list) {
    document.getElementById(host).innerHTML = list.map(function (x) {
      return '<div class="tile"><div class="v">' + x.v + '</div><div class="k">' + S.esc(x.k) +
        '</div><div class="d">' + S.esc(x.d) + "</div></div>";
    }).join("");
  }

  tiles("tiles", [
    { v: S.num(t.record_count), k: "Landlord-tenant records", d: "district-assigned" },
    { v: S.num(t.unique_addresses), k: "Distinct addresses", d:
      (t.record_count / t.unique_addresses).toFixed(1) + " records per address" },
    { v: S.pct(ic.no_lastinspdate_pct), k: "No recorded LastInspDate",
      d: S.num(ic.no_lastinspdate) + " of " + S.num(t.record_count) },
    { v: S.pct(sc.substantive_pct), k: "Classified substantive",
      d: S.num(sc.substantive_complaints) + " records" }
  ]);

  // ---- record type mix -----------------------------------------------------
  var known = t.cp_count + t.vi_count + t.ct_count;
  var other = t.record_count - known;
  S.barChartH(document.getElementById("mix"), {
    title: "Record types in District " + id,
    sub: "SDCI RECORDTYPE, district-assigned landlord-tenant records",
    cats: ["Complaints (CP)", "Violations / NOV (VI)", "Tenant relocation (CT)", "Other record types"],
    values: [t.cp_count, t.vi_count, t.ct_count, other],
    notes: [t.cp_count, t.vi_count, t.ct_count, other].map(function (v) {
      return (v / t.record_count * 100).toFixed(1) + "% of this district's records";
    }),
    labelW: 220, unit: "records", seriesName: "Records", catLabel: "Record type",
    caption: "Complaint, violation and relocation records do not sum to the district total; " +
             S.num(other) + " records carry other SDCI record types."
  });

  // ---- SDCI's own description field ---------------------------------------
  document.getElementById("comp-note").innerHTML =
    "<b>SDCI's own <code>RECORDTYPEDESC</code> field is blank on " + S.pct(comp.blank_pct) +
    " of this district's records</b> (" + S.num(comp.blank) + " of " + S.num(t.record_count) +
    "). These are records already confirmed as landlord-tenant cases through the " +
    "<code>RECORDTYPE</code> field, so the blank describes SDCI's own descriptive completeness — " +
    "it is not a reclassification by STLCA, and it does not change what the record is.";

  S.barChartH(document.getElementById("comp"), {
    title: "RECORDTYPEDESC values on confirmed landlord-tenant records",
    sub: "District " + id + " · documents SDCI's descriptive completeness, not a reclassification",
    cats: ["(blank)", "Landlord-tenant, explicit", "Emergency + landlord-tenant",
           "Emergency only", "Other mixed categories"],
    values: [comp.blank, comp.landlord_tenant_explicit, comp.emergency_plus_lt,
             comp.emergency_only, comp.other_mixed_categories],
    labelW: 240, unit: "records", seriesName: "Records", catLabel: "RECORDTYPEDESC",
    caption: "A blank description field does not make a record less of a landlord-tenant case."
  });

  // ---- NOV-to-complaint record ratio over time ----------------------------
  var years = Object.keys(d.enforcement_gap.by_year).sort();
  var cp = years.map(function (y) { return d.enforcement_gap.by_year[y].cp; });
  var vi = years.map(function (y) { return d.enforcement_gap.by_year[y].vi; });
  var ratio = years.map(function (y) { return d.enforcement_gap.by_year[y].vi_to_cp_pct; });

  S.barChart(document.getElementById("cpvi"), {
    title: "Complaint and violation records opened per year — District " + id,
    sub: "Both series are record counts, so they share one axis",
    cats: years, catLabel: "Year",
    series: [{ name: "Complaints (CP)", values: cp }, { name: "Violations / NOV (VI)", values: vi }],
    height: 290, labelEvery: 2,
    caption: "Counts of records opened in each year, by SDCI record type."
  });

  S.lineChart(document.getElementById("ratio"), {
    title: "NOV-to-complaint record ratio — District " + id,
    sub: "VI records divided by CP records, by year. A record ratio, not a conversion rate.",
    cats: years, catLabel: "Year",
    series: [{ name: "NOV-to-complaint record ratio", values: ratio }],
    fmt: function (v) { return v.toFixed(0) + "%"; },
    height: 280, labelEvery: 2, max: 100,
    caption: "This is VI divided by CP within each year. It does not measure whether any particular " +
             "complaint led to a violation — the record does not link them that way."
  });

  // ---- what tenants reported ----------------------------------------------
  S.barChartH(document.getElementById("habit"), {
    title: "Substantive complaint categories — District " + id,
    sub: "Approved classifier rule set · a record can match more than one group",
    cats: ["Habitability &amp; life safety", "Eviction &amp; displacement",
           "Rent &amp; financial", "Security &amp; access"].map(function (s) {
             return s.replace("&amp;", "&"); }),
    values: [hc.habitability_life_safety, hc.eviction_displacement,
             hc.rent_financial, hc.security_access],
    labelW: 210, unit: "records", seriesName: "Records", catLabel: "Category",
    caption: "Groups come from the approved classifier rule set. Overlapping matches mean these do " +
             "not sum to the substantive total of " + S.num(sc.substantive_complaints) + "."
  });

  var sig = sc.top_signals, keys = Object.keys(sig).slice(0, 10);
  document.querySelector("#signals tbody").innerHTML = keys.map(function (k) {
    var src = k.indexOf("csv:") === 0 ? "SDCI field value" : "keyword match";
    return "<tr><td>" + S.esc(k.replace(/^(csv|kw):/, "").replace(/_/g, " ")) +
      "</td><td>" + src + "</td><td>" + S.num(sig[k]) + "</td></tr>";
  }).join("");

  // ---- resolution time, including the anomaly ------------------------------
  var p = rt.percentiles;
  tiles("rt-tiles", [
    { v: S.num(rt.median) + " days", k: "Median recorded resolution time",
      d: "n = " + S.num(rt.count) + " records with both dates" },
    { v: S.num(Math.round(rt.mean)) + " days", k: "Mean recorded resolution time",
      d: "std " + S.num(Math.round(rt.std)) + " days" },
    { v: S.num(p["90"]) + " days", k: "90th percentile", d: "99th: " + S.num(p["99"]) + " days" }
  ]);

  S.barChartH(document.getElementById("rt-dist"), {
    title: "Recorded resolution time by percentile — District " + id,
    sub: "Days between the recorded open and close dates · n = " + S.num(rt.count),
    cats: ["25th", "50th (median)", "75th", "90th", "95th", "99th"],
    values: [p["25"], p["50"], p["75"], p["90"], p["95"], p["99"]],
    labelW: 150, unit: "days", seriesName: "Days", catLabel: "Percentile",
    fmt: function (v) { return S.num(Math.round(v)) + "d"; },
    caption: "Percentiles of the recorded interval. This measures what the dates say, not how long " +
             "any underlying condition persisted."
  });

  if (rt.min < 0) {
    document.getElementById("rt-anomaly").innerHTML =
      "<b>Negative intervals are present in this district's dates</b>" +
      "<p style='margin:6px 0 0'>The minimum recorded interval is " + S.num(rt.min) +
      " days, meaning the recorded close date precedes the recorded open date on at least one " +
      "record. STLCA reports this as a date-integrity observation in the source export. It is not " +
      "evidence of backdating, and no such claim is made here — it establishes only that the two " +
      "date fields are not internally consistent on every record, which is itself a limit on what " +
      "any timing figure from this field can support.</p>";
  } else {
    document.getElementById("rt-anomaly").hidden = true;
  }

  // ---- limitations & provenance -------------------------------------------
  document.getElementById("verbatim").textContent = f.inspection_date_limitation;

  document.getElementById("prov").innerHTML =
    "<b>District</b> " + id + " — " + S.esc(d.name) + "<br>" +
    "<b>Source</b> " + S.esc(d.source.file) + "<br>" +
    "<b>SHA-256</b> " + d.source.sha256 + "<br>" +
    "<b>Method</b> " + S.esc(d.source.methodology) + "<br>" +
    "<b>Universe</b> " + S.num(t.record_count) + " district records, drawn from the " +
    S.num(d.source.citywide_llt_universe) + "-record landlord-tenant universe (" +
    S.num(f.universe.assigned_to_district) + " district-assigned citywide)<br>" +
    "<b>Date scope</b> through " + f.universe.through +
    " · <b>QA</b> " + D.reconciliation.status + " against the published assigned total<br>" +
    "<b>Classifier</b> " + S.esc(sc.method) + "<br>" +
    "<b>Data layer built</b> " + D.generated;

  // sibling navigation
  document.getElementById("siblings").innerHTML = Object.keys(D.districts).sort().map(function (i) {
    return i === id
      ? '<span class="pill">D' + i + "</span>"
      : '<a class="pill" style="background:transparent;color:inherit;border:1px solid var(--screen-rule);text-decoration:none" href="district-' + i + '.html">D' + i + "</a>";
  }).join(" ");
})();
