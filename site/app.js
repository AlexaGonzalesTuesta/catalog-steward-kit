/* Catalog Steward Kit: steward review screen.
   Reads data/snapshot.json (written by `python -m steward_kit scan`).
   Decisions are kept in this browser only, so every visitor works in a private copy. */
(function () {
  "use strict";

  var SNAPSHOT_URL = "data/snapshot.json";
  var app = document.getElementById("app");
  var state = { snap: null, decisions: {}, tab: "queue", steward: "", type: "", openSql: {}, errors: {}, drafts: {} };
  var memoryStore = {};

  var TYPE_LABELS = { pii: "PII review", quality: "Quality check", classify: "Classification",
                      owner: "Data owner", describe: "Description" };

  // ---------- helpers ----------
  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else if (k.indexOf("on") === 0) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }
  function fmt(n) { return n === null || n === undefined ? "-" : Number(n).toLocaleString("en-US"); }
  function sqlLiteral(v) { return "'" + String(v).replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'"; }
  function stewardName(email) {
    var s = (state.snap.stewards || []).filter(function (x) { return x.email === email; })[0];
    return s ? s.name : email;
  }
  function storageKey() {
    return "csk.decisions.v1:" + state.snap.catalog.name + ":" + state.snap.catalog.scanned_at;
  }
  function loadDecisions() {
    try { return JSON.parse(window.localStorage.getItem(storageKey()) || "{}"); }
    catch (e) { return memoryStore[storageKey()] || {}; }
  }
  function saveDecisions() {
    try { window.localStorage.setItem(storageKey(), JSON.stringify(state.decisions)); }
    catch (e) { memoryStore[storageKey()] = state.decisions; }
  }

  // ---------- derived state ----------
  function itemsFor(table, type) {
    return state.snap.items.filter(function (i) { return i.table === table && i.type === type; });
  }
  function tableView(t) {
    var v = Object.assign({}, t);
    itemsFor(t.table, "owner").forEach(function (i) { if (state.decisions[i.id]) v.data_owner = state.decisions[i.id].value; });
    itemsFor(t.table, "describe").forEach(function (i) { if (state.decisions[i.id]) v.description = state.decisions[i.id].value; });
    itemsFor(t.table, "classify").forEach(function (i) { if (state.decisions[i.id]) v.classification = state.decisions[i.id].value; });
    var pii = itemsFor(t.table, "pii");
    v.open_pii = pii.filter(function (i) { return !state.decisions[i.id]; }).length;
    v.confirmed_pii = pii.filter(function (i) { return state.decisions[i.id] && state.decisions[i.id].decision === "confirm"; }).length;
    v.ready = !!(v.description && v.data_owner && v.classification && v.open_pii === 0);
    return v;
  }
  function metrics() {
    var tables = state.snap.tables.map(tableView);
    var m = state.snap.metrics;
    return {
      ready: tables.filter(function (t) { return t.ready; }).length,
      readyBase: m.tables_ready, tables: m.tables,
      openPii: tables.reduce(function (a, t) { return a + t.open_pii; }, 0), openPiiBase: m.open_pii,
      qualityFailing: m.quality_failing, qualityRules: m.quality_rules,
      stewardsReady: m.stewards_ready, stewards: m.stewards
    };
  }
  function suggestedLevel(item) {
    var t = state.snap.tables.filter(function (x) { return x.table === item.table; })[0];
    var v = t ? tableView(t) : null;
    if (v && (v.confirmed_pii > 0 || t.contains_pii)) return state.snap.policy.pii_level;
    if (v && v.open_pii > 0) return state.snap.policy.pii_level;
    return item.suggested;
  }
  function decisionCount() { return Object.keys(state.decisions).length; }

  function buildSql() {
    var lines = [
      "-- Catalog Steward Kit decisions for catalog " + state.snap.catalog.name,
      "-- Scan: " + state.snap.catalog.scanned_at + "   Exported: " + new Date().toISOString(),
      "-- Run in a Databricks SQL editor as a user who owns these tables (or has APPLY TAG and MODIFY).",
      ""
    ];
    state.snap.items.forEach(function (i) {
      var d = state.decisions[i.id];
      if (!d) return;
      var sql = null;
      if (i.type === "pii") sql = d.decision === "confirm" ? i.sql_confirm : i.sql_reject;
      else if (i.sql) sql = i.sql.replace("{value}", sqlLiteral(d.value));
      if (!sql) return;
      var what = i.type === "pii" ? (d.decision === "confirm" ? "Confirmed PII: " : "Not PII: ") + i.object
                                  : TYPE_LABELS[i.type] + ": " + i.object;
      lines.push("-- " + what, sql, "");
    });
    return lines.join("\n");
  }
  function download() {
    var blob = new Blob([buildSql()], { type: "text/plain" });
    var a = el("a", { href: URL.createObjectURL(blob),
                      download: "steward-decisions-" + new Date().toISOString().slice(0, 10) + ".sql" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  // ---------- actions ----------
  function decide(item, decision, value) {
    state.decisions[item.id] = { decision: decision, value: value === undefined ? null : value, at: new Date().toISOString() };
    delete state.errors[item.id];
    saveDecisions(); render();
  }
  function undo(item) { delete state.decisions[item.id]; saveDecisions(); render(); }
  function clearAll() {
    if (!decisionCount()) return;
    state.decisions = {}; saveDecisions(); render();
  }
  function jumpTo(itemId, opts) {
    state.tab = "queue"; state.steward = ""; state.type = "";
    if (opts && opts.openSql) state.openSql[itemId] = true;
    render();
    var n = document.getElementById("item-" + itemId);
    if (n) {
      n.scrollIntoView({ behavior: "smooth", block: "center" });
      n.classList.add("flash");
      setTimeout(function () { n.classList.remove("flash"); }, 1400);
      var focusable = n.querySelector("button, input, select, textarea");
      if (focusable) focusable.focus({ preventScroll: true });
    }
  }

  // ---------- rendering ----------
  function renderHeader() {
    var c = state.snap.catalog;
    var catalogLabel = document.getElementById("catalogLabel");
    catalogLabel.innerHTML = "";
    catalogLabel.appendChild(el("code", { text: c.name }));
    catalogLabel.appendChild(document.createTextNode(" · " + c.display_name));
    var when = new Date(c.scanned_at);
    var scanned = document.getElementById("scannedLabel");
    scanned.innerHTML = "";
    scanned.appendChild(document.createTextNode("Scanned " + when.toLocaleString("en-US",
      { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) + " · "));
    scanned.appendChild(el("a", { href: "#sources", text: "Data sources" }));
  }

  function kpi(label, value, note) {
    return el("div", { class: "kpi" }, [el("div", { class: "label", text: label }), value, el("div", { class: "note" }, note ? [note] : [])]);
  }
  function renderKpis() {
    var m = metrics();
    var readyNote = m.ready > m.readyBase
      ? el("span", { class: "delta", text: "+" + (m.ready - m.readyBase) + " from your decisions" })
      : "Described, owned, classified and PII reviewed";
    var piiNote = m.openPii < m.openPiiBase
      ? el("span", { class: "delta", text: (m.openPiiBase - m.openPii) + " decided by you" })
      : "Columns that may hold personal data";
    return el("section", { class: "kpis", "aria-label": "Catalog health" }, [
      kpi("Governance-ready tables", el("div", { class: "value" }, [String(m.ready), el("small", { text: " of " + m.tables })]), readyNote),
      kpi("PII reviews open", el("div", { class: "value", text: String(m.openPii) }), piiNote),
      kpi("Failing quality checks", el("div", { class: "value" }, [String(m.qualityFailing), el("small", { text: " of " + m.qualityRules })]),
          "Rules in governance.yml"),
      kpi("Stewards ready to review", el("div", { class: "value" }, [String(m.stewardsReady), el("small", { text: " of " + m.stewards })]),
          "Training, access and first review done")
    ]);
  }

  function renderTry() {
    var items = state.snap.items;
    var pii = items.filter(function (i) { return i.type === "pii"; })[0];
    var owner = items.filter(function (i) { return i.type === "owner"; })[0];
    var dq = items.filter(function (i) { return i.type === "quality" && i.priority === "high"; })[0] ||
             items.filter(function (i) { return i.type === "quality"; })[0];
    var links = [];
    if (pii) links.push(el("a", { tabindex: "0", onclick: function () { jumpTo(pii.id); },
      onkeydown: function (e) { if (e.key === "Enter") jumpTo(pii.id); }, text: "confirm a suggested PII tag" }));
    if (owner) links.push(el("a", { tabindex: "0", onclick: function () { jumpTo(owner.id); },
      onkeydown: function (e) { if (e.key === "Enter") jumpTo(owner.id); }, text: "assign a missing data owner" }));
    if (dq) links.push(el("a", { tabindex: "0", onclick: function () { jumpTo(dq.id, { openSql: true }); },
      onkeydown: function (e) { if (e.key === "Enter") jumpTo(dq.id, { openSql: true }); }, text: "open a failing quality check" }));
    if (!links.length) return null;
    var parts = ["Try it: "];
    links.forEach(function (l, i) { parts.push(l); if (i < links.length - 1) parts.push(" · "); });
    return el("p", { class: "try" }, parts);
  }

  function renderTabs() {
    var open = state.snap.items.filter(function (i) { return !state.decisions[i.id]; }).length;
    var tabs = [["queue", "Work queue", open], ["health", "Catalog health", null],
                ["quality", "Quality checks", null], ["stewards", "Stewards", null]];
    return el("div", { class: "tabs", role: "tablist" }, tabs.map(function (t) {
      return el("button", { class: "tab", role: "tab", type: "button", id: "tab-" + t[0],
        "aria-selected": state.tab === t[0] ? "true" : "false",
        onclick: function () { state.tab = t[0]; render(); } },
        [t[1], t[2] !== null ? el("span", { class: "count", text: String(t[2]) }) : null]);
    }));
  }

  function filteredItems() {
    return state.snap.items.filter(function (i) {
      return (!state.steward || i.steward === state.steward) && (!state.type || i.type === state.type);
    });
  }

  function renderToolbar() {
    var counts = {};
    state.snap.items.forEach(function (i) { counts[i.steward] = (counts[i.steward] || 0) + 1; });
    var stewardSel = el("select", { "aria-label": "Steward", onchange: function (e) { state.steward = e.target.value; render(); } },
      [el("option", { value: "", text: "All stewards" })].concat(state.snap.stewards.map(function (s) {
        return el("option", { value: s.email, text: s.name + " (" + (counts[s.email] || 0) + ")", selected: state.steward === s.email });
      })));
    var types = ["pii", "quality", "classify", "owner", "describe"];
    var typeSel = el("select", { "aria-label": "Type", onchange: function (e) { state.type = e.target.value; render(); } },
      [el("option", { value: "", text: "All types" })].concat(types.map(function (t) {
        return el("option", { value: t, text: TYPE_LABELS[t], selected: state.type === t });
      })));
    var n = decisionCount();
    return el("div", { class: "toolbar" }, [
      el("label", {}, ["Steward", stewardSel]),
      el("label", {}, ["Type", typeSel]),
      el("span", { class: "spacer" }),
      el("span", { class: "decisions", text: n ? n + (n === 1 ? " decision" : " decisions") + " ready to apply" : "No decisions yet" }),
      n ? el("button", { type: "button", class: "link", onclick: clearAll, text: "Clear" }) : null,
      el("button", { type: "button", class: "btn", disabled: n ? null : true, onclick: download,
        title: "Download a .sql file to run in Databricks", text: "Download SQL" })
    ]);
  }

  function decidedSummary(item, d) {
    var text;
    if (item.type === "pii") text = d.decision === "confirm" ? "Confirmed PII (" + item.pii_type.replace("_", " ") + ")" : "Marked not PII";
    else if (item.type === "owner") text = "Owner set to " + d.value;
    else if (item.type === "classify") text = "Classified " + d.value;
    else text = "Description saved";
    return el("div", { class: "done" }, [el("strong", { text: text }), " · ",
      el("button", { type: "button", class: "link", onclick: function () { undo(item); }, text: "Undo" })]);
  }

  function actionFor(item) {
    var d = state.decisions[item.id];
    if (d) return decidedSummary(item, d);
    var err = state.errors[item.id] ? el("div", { class: "err", text: state.errors[item.id] }) : null;
    if (item.type === "pii") {
      return el("div", { class: "row" }, [
        el("button", { type: "button", class: "btn", onclick: function () { decide(item, "confirm"); }, text: "Confirm PII" }),
        el("button", { type: "button", class: "btn secondary", onclick: function () { decide(item, "reject"); }, text: "Not PII" })
      ]);
    }
    if (item.type === "owner") {
      var input = el("input", { type: "text", value: state.drafts[item.id] !== undefined ? state.drafts[item.id] : (item.suggested || ""),
                                "aria-label": "Data owner for " + item.object, placeholder: "owner@company.com or group",
                                oninput: function (e) { state.drafts[item.id] = e.target.value; } });
      return el("div", {}, [el("div", { class: "row" }, [input, el("button", { type: "button", class: "btn", text: "Set owner",
        onclick: function () {
          var v = input.value.trim();
          if (!v) { state.errors[item.id] = "Enter an owner email or group."; render(); return; }
          decide(item, "set", v);
        } })]), err]);
    }
    if (item.type === "describe") {
      var ta = el("textarea", { "aria-label": "Description for " + item.object, placeholder: "What the table holds, its grain and where it comes from",
                                oninput: function (e) { state.drafts[item.id] = e.target.value; } });
      ta.value = state.drafts[item.id] || "";
      return el("div", {}, [ta, el("div", { class: "row" }, [el("button", { type: "button", class: "btn", text: "Save description",
        onclick: function () {
          var v = ta.value.trim();
          if (v.length < 15) { state.errors[item.id] = "Write at least one full sentence."; render(); return; }
          decide(item, "set", v);
        } })]), err]);
    }
    if (item.type === "classify") {
      var level = suggestedLevel(item);
      var sel = el("select", { "aria-label": "Classification for " + item.object },
        item.levels.map(function (l) { return el("option", { value: l, text: l, selected: l === level }); }));
      return el("div", { class: "row" }, [sel, el("button", { type: "button", class: "btn", text: "Set level",
        onclick: function () { decide(item, "set", sel.value); } })]);
    }
    if (item.type === "quality") {
      var open = !!state.openSql[item.id];
      return el("div", { class: "row" }, [el("button", { type: "button", class: "btn secondary",
        "aria-expanded": open ? "true" : "false",
        onclick: function () { state.openSql[item.id] = !open; render(); },
        text: open ? "Hide failing rows query" : "Show failing rows query" })]);
    }
    return null;
  }

  function renderItem(item) {
    var d = state.decisions[item.id];
    var meta = [TYPE_LABELS[item.type], stewardName(item.steward)];
    if (item.confidence !== undefined) meta.push("confidence " + Math.round(item.confidence * 100) + "%");
    var body = el("div", { class: "body" }, [
      el("div", { class: "obj", text: item.object }),
      el("div", { class: "title", text: item.title }),
      el("div", { class: "evidence", text: item.evidence }),
      item.examples && item.examples.length ? el("div", { class: "examples" },
        [el("span", { class: "subtle", text: "Masked samples:" })].concat(item.examples.map(function (x) { return el("code", { text: x }); }))) : null,
      el("div", { class: "meta", text: meta.join(" · ") })
    ]);
    var children = [el("div", { class: "prio " + item.priority, text: item.priority }), body, el("div", { class: "action" }, [actionFor(item)])];
    if (item.type === "quality" && state.openSql[item.id] && item.query) {
      children.push(el("div", {}, []));
      children.push(el("pre", { class: "sql", text: item.query }));
    }
    return el("article", { class: "item" + (d ? " decided" : ""), id: "item-" + item.id }, children);
  }

  function renderQueue() {
    var list = filteredItems();
    var body;
    if (!state.snap.items.length) body = el("div", { class: "empty", text: "Nothing to review. Every table is described, owned, classified and passing its checks." });
    else if (!list.length) body = el("div", { class: "empty", text: "No open items match these filters." });
    else {
      var undecided = list.filter(function (i) { return !state.decisions[i.id]; });
      var ordered = undecided.concat(list.filter(function (i) { return state.decisions[i.id]; }));
      body = el("div", {}, ordered.map(renderItem));
      if (!undecided.length) body.insertBefore(el("div", { class: "empty", text: "Every item in this view has a decision. Download the SQL to apply them in Databricks." }), body.firstChild);
    }
    return el("section", { role: "tabpanel", "aria-labelledby": "tab-queue" }, [renderToolbar(), el("div", { class: "queue" }, [body])]);
  }

  function yesNo(value, okText) {
    return value ? el("span", { class: "tag ok", text: okText || "Yes" }) : el("span", { class: "tag missing", text: "Missing" });
  }

  function renderHealth() {
    var rows = state.snap.tables.map(tableView);
    var head = ["Table", "Steward", "Rows", "Description", "Data owner", "Classification", "Columns described", "PII review", "Quality", "Ready"];
    return el("section", { role: "tabpanel", "aria-labelledby": "tab-health" }, [
      el("p", { class: "section-note", text: "A table is governance-ready when it has a description, a data owner, a classification and no open PII reviews. Your decisions update this view." }),
      el("div", { class: "grid-wrap" }, [el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, head.map(function (h) { return el("th", { text: h }); }))]),
        el("tbody", {}, rows.map(function (r) {
          return el("tr", {}, [
            el("td", { class: "mono" }, [r.table, r.synthetic ? el("div", { class: "subtle", text: "synthetic data" }) : null]),
            el("td", { text: stewardName(r.steward) }),
            el("td", { class: "num", text: fmt(r.rows) }),
            el("td", {}, [yesNo(r.description)]),
            el("td", {}, [r.data_owner ? el("span", { class: "subtle", text: r.data_owner }) : yesNo(false)]),
            el("td", {}, [r.classification ? el("span", { class: "tag plain", text: r.classification }) : yesNo(false)]),
            el("td", { class: "num", text: r.columns_described + " of " + r.columns }),
            el("td", {}, [r.open_pii ? el("span", { class: "tag warn", text: r.open_pii + " open" }) : el("span", { class: "tag ok", text: "Done" })]),
            el("td", {}, [r.quality_failing ? el("span", { class: "tag missing", text: r.quality_failing + " of " + r.quality_rules + " failing" })
                                            : el("span", { class: "tag ok", text: r.quality_rules ? "Passing" : "No rules" })]),
            el("td", {}, [r.ready ? el("span", { class: "tag ok", text: "Ready" }) : el("span", { class: "tag plain", text: "Not yet" })])
          ]);
        }))
      ])])
    ]);
  }

  function renderQuality() {
    var order = { fail: 0, error: 1, pass: 2 };
    var rows = state.snap.quality.slice().sort(function (a, b) { return order[a.status] - order[b.status] || a.id.localeCompare(b.id); });
    var head = ["Rule", "What it checks", "Table", "Severity", "Result", ""];
    var body = [];
    rows.forEach(function (q) {
      var open = !!state.openSql["q-" + q.id];
      var tag = q.status === "pass" ? el("span", { class: "tag ok", text: "Pass" })
              : q.status === "fail" ? el("span", { class: "tag missing", text: "Fail" }) : el("span", { class: "tag warn", text: "Error" });
      body.push(el("tr", {}, [
        el("td", { class: "mono", text: q.id }),
        el("td", {}, [q.description, el("div", { class: "subtle", text: q.check.replace("_", " ") + (q.column ? " on " + q.column : "") })]),
        el("td", { class: "mono", text: q.table }),
        el("td", { text: q.severity }),
        el("td", {}, [tag, el("div", { class: "subtle", text: q.detail })]),
        el("td", {}, [q.status !== "pass" && q.sql ? el("button", { type: "button", class: "link", "aria-expanded": open ? "true" : "false",
          onclick: function () { state.openSql["q-" + q.id] = !open; render(); }, text: open ? "Hide query" : "Query" }) : null])
      ]));
      if (open) body.push(el("tr", {}, [el("td", { colspan: "6" }, [el("pre", { class: "sql", text: q.sql })])]));
    });
    return el("section", { role: "tabpanel", "aria-labelledby": "tab-quality" }, [
      el("p", { class: "section-note", text: "Each rule in governance.yml runs as SQL against the catalog. The query returns the failing rows so the steward can hand them to the data producer." }),
      el("div", { class: "grid-wrap" }, [el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, head.map(function (h) { return el("th", { text: h }); }))]), el("tbody", {}, body)])])
    ]);
  }

  function renderStewards() {
    var repo = document.body.getAttribute("data-repo");
    var head = ["Steward", "Domain", "Required learning", "Catalog access", "First review", "Open items", "Status"];
    return el("section", { role: "tabpanel", "aria-labelledby": "tab-stewards" }, [
      el("p", { class: "section-note" }, ["Stewards can review once they finish required learning, have approved catalog access and complete a first review with a mentor. The ",
        el("a", { href: repo + "/blob/main/docs/steward-quick-start.md", text: "steward quick start" }), " lists each step."]),
      el("div", { class: "grid-wrap" }, [el("table", { class: "grid" }, [
        el("thead", {}, [el("tr", {}, head.map(function (h) { return el("th", { text: h }); }))]),
        el("tbody", {}, state.snap.stewards.map(function (s) {
          return el("tr", {}, [
            el("td", {}, [s.name, el("div", { class: "subtle", text: s.email })]),
            el("td", { text: s.domain_name }),
            el("td", {}, [yesNo(s.required_learning, "Done")]),
            el("td", {}, [yesNo(s.catalog_access, "Approved")]),
            el("td", {}, [yesNo(s.first_review, "Done")]),
            el("td", { class: "num", text: String(s.open_items) }),
            el("td", {}, [s.ready ? el("span", { class: "tag ok", text: "Ready" }) : el("span", { class: "tag warn", text: "Onboarding" })])
          ]);
        }))
      ])])
    ]);
  }

  function renderSources() {
    var src = state.snap.sources || {};
    var list = Object.keys(src).map(function (k) {
      var s = src[k];
      var when = s.fetched_at ? " · fetched " + s.fetched_at.slice(0, 10) : "";
      return el("li", {}, [s.url ? el("a", { href: s.url, text: s.source || k }) : (s.source || k),
        (s.rows ? " · " + fmt(s.rows) + " rows" : "") + (s.scope ? " · " + s.scope : "") + when]);
    });
    var repo = document.body.getAttribute("data-repo");
    return el("footer", { class: "sources", id: "sources" }, [
      el("strong", { text: "Data sources" }),
      list.length ? el("ul", {}, list) : el("p", { text: "Scanned from a live Databricks workspace." }),
      state.snap.synthetic_tables.length ? el("p", { text: state.snap.synthetic_tables.join(" and ") +
        " are synthetic. Every person in them is fictional: emails use reserved example domains and phone numbers use the 555-01xx range." }) : null,
      el("p", {}, ["Source code, setup and evaluation results: ", el("a", { href: repo, text: repo.replace("https://", "") })])
    ]);
  }

  function render() {
    if (!state.snap) return;
    var panels = { queue: renderQueue, health: renderHealth, quality: renderQuality, stewards: renderStewards };
    var scrollY = window.scrollY;
    var activeId = document.activeElement && document.activeElement.id;
    app.innerHTML = "";
    app.appendChild(el("h1", { class: "lead", text: "Confirm or reject each suggested PII tag, fill in missing owners and descriptions, then download the SQL to apply your decisions in Databricks." }));
    var t = renderTry(); if (t) app.appendChild(t);
    app.appendChild(renderKpis());
    app.appendChild(renderTabs());
    app.appendChild(panels[state.tab]());
    app.appendChild(renderSources());
    window.scrollTo(0, scrollY);
    if (activeId) { var a = document.getElementById(activeId); if (a) a.focus({ preventScroll: true }); }
  }

  function showError(message) {
    app.innerHTML = "";
    var node = document.getElementById("tpl-error").content.cloneNode(true);
    node.querySelector(".detail").textContent = message;
    node.querySelector("[data-action=retry]").addEventListener("click", load);
    app.appendChild(node);
  }

  function load() {
    app.innerHTML = "";
    app.appendChild(el("p", { class: "state", text: "Loading the latest catalog scan…" }));
    fetch(SNAPSHOT_URL, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("The server answered " + r.status + " for " + SNAPSHOT_URL + ".");
        return r.json();
      })
      .then(function (snap) {
        if (!snap || !snap.catalog || !Array.isArray(snap.items)) throw new Error("snapshot.json is not a Catalog Steward Kit scan.");
        state.snap = snap;
        state.decisions = loadDecisions();
        renderHeader();
        render();
      })
      .catch(function (e) {
        var offline = navigator.onLine === false;
        showError(offline ? "You are offline and no scan has been loaded yet. Reconnect and try again."
                          : (e && e.message ? e.message : "Unknown error.") + " If you opened index.html directly from disk, run: python -m http.server -d site 8000");
      });
  }

  function updateOnline() { document.getElementById("offline").hidden = navigator.onLine !== false; }
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
  updateOnline();
  load();
})();
