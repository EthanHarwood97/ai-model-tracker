const $ = (sel) => document.querySelector(sel);
const state = { sort: { key: null, dir: -1 }, data: {} };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function num(v, digits = 2) {
  return v === null || v === undefined ? "&mdash;" : Number(v).toFixed(digits);
}

function money(v) {
  if (v === null || v === undefined) return "&mdash;";
  if (v < 0.01) return `$${v.toFixed(3)}`;
  if (v < 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(2)}`;
}

function badges(e) {
  let b = "";
  if (e.measured) b += '<span class="badge measured">MEASURED</span> ';
  else b += '<span class="badge est">EST</span> ';
  if (e.is_new) b += '<span class="badge new">NEW</span> ';
  const d = e.detail || {};
  if (d.quirky_family) b += '<span class="badge warn">quirky family</span> ';
  if (d.agrees === false) b += '<span class="badge warn">regressions disagree</span> ';
  return b || "&mdash;";
}

function sourcesChips(e) {
  const srcs = e.detail && e.detail.coding_sources ? e.detail.coding_sources : null;
  const comps = e.components || {};
  const all = [];
  for (const cat of Object.keys(comps)) {
    for (const s of comps[cat].sources) all.push(s.source);
  }
  return [...new Set(all)].map((s) => `<span class="badge src">${esc(s)}</span>`).join(" ");
}

function metaBand(e) {
  if (e.meta_min === null || e.meta_max === null) return "";
  return `<span class="${e.measured ? "muted" : "est-range"}">${num(e.meta_min, 1)}&ndash;${num(e.meta_max, 1)}</span>`;
}

function codingBar(v, max, measured) {
  const pct = max > 0 ? Math.round((v / max) * 100) : 0;
  return `<span class="bar ${measured ? "" : "bar-est"}" style="width:${Math.max(4, pct)}%"></span> ${num(v)}`;
}

function metaRow(e) {
  const harness = e.harness ? `<div class="harness">${esc(e.harness)}</div>` : "";
  const est = !e.measured && e.detail ? `<div class="est-range">&plusmn;${num(e.detail.band ?? e.band ?? 0.06, 2)} &middot; pred ${num(e.detail.est_from_intelligence, 2)}</div>` : "";
  return `<tr>
    <td class="model-cell">${esc(e.name)}${harness}${est}</td>
    <td>${badges(e)}</td>
    <td>${num(e.meta)}</td>
    <td>${metaBand(e)}</td>
    <td>${codingBar(e.coding_index, 100, e.measured)}</td>
    <td>${num(e.intelligence)}</td>
    <td>${e.n_sources}</td>
    <td>${money(e.price_mtok)}</td>
    <td>${money(e.cost_task)}</td>
    <td>${sourcesChips(e)}</td>
  </tr>`;
}

function metaHead() {
  return `<tr>
    <th data-key="name">Model</th>
    <th data-key="measured">Badge</th>
    <th data-key="meta">Meta</th>
    <th data-key="meta_min">Band</th>
    <th data-key="coding_index">Coding idx</th>
    <th data-key="intelligence">Intelligence</th>
    <th data-key="n_sources"># sources</th>
    <th data-key="price_mtok">$/Mtok</th>
    <th data-key="cost_task">$/task</th>
    <th>Sources</th>
  </tr>`;
}

function codingRow(e, max) {
  const harness = e.harness ? `<div class="harness">${esc(e.harness)}</div>` : "";
  return `<tr>
    <td class="model-cell">${esc(e.name)}${harness}</td>
    <td>${badges(e)}</td>
    <td>${codingBar(e.coding_index, max, true)}</td>
    <td>${num(e.meta)}</td>
    <td>${num(e.intelligence)}</td>
    <td>${money(e.price_mtok)}</td>
    <td>${money(e.cost_task)}</td>
    <td>${num(e.wall_time_s, 0)}s</td>
    <td>${sourcesChips(e)}</td>
  </tr>`;
}

function codingHead() {
  return `<tr>
    <th data-key="name">Model</th>
    <th data-key="measured">Badge</th>
    <th data-key="coding_index">Coding idx</th>
    <th data-key="meta">Meta</th>
    <th data-key="intelligence">Intelligence</th>
    <th data-key="price_mtok">$/Mtok</th>
    <th data-key="cost_task">$/task</th>
    <th data-key="wall_time_s">Wall time</th>
    <th>Sources</th>
  </tr>`;
}

function estRow(e) {
  const d = e.detail || {};
  const warn = d.quirky_family ? " &middot; <span class='badge warn'>quirky family</span>" : "";
  const agree = d.agrees === true ? '<span class="pos">&check; agree</span>' : d.agrees === false ? '<span class="neg">&#10007; disagree</span>' : "&mdash;";
  return `<tr>
    <td class="model-cell">${esc(e.name)}</td>
    <td><span class="badge est">EST</span></td>
    <td>${codingBar(e.coding_index, 100, false)}</td>
    <td class="est-range">&plusmn;${num(d.band ?? e.band ?? 0.06, 2)}</td>
    <td>${num(e.intelligence)}</td>
    <td>${num(d.est_from_intelligence, 3)} / ${num(d.est_from_coding_index, 3)}</td>
    <td>${agree}${warn}</td>
    <td>${money(e.price_mtok)}</td>
    <td>${num(e.meta)}</td>
  </tr>`;
}

function estHead() {
  return `<tr>
    <th data-key="name">Model</th>
    <th>Badge</th>
    <th data-key="coding_index">Est coding idx</th>
    <th>Band</th>
    <th data-key="intelligence">Intelligence</th>
    <th>Pred (int / code regr)</th>
    <th>Agreement</th>
    <th data-key="price_mtok">$/Mtok</th>
    <th data-key="meta">Meta</th>
  </tr>`;
}

function valueRow(e) {
  const idx = e.coding_index || 0;
  const cost = e.cost_task ?? e.price_mtok;
  const ratio = cost ? idx / cost : null;
  return `<tr>
    <td class="model-cell">${esc(e.name)}</td>
    <td>${badges(e)}</td>
    <td>${num(idx)}</td>
    <td>${money(e.cost_task)}</td>
    <td>${money(e.price_mtok)}</td>
    <td>${num(ratio)}</td>
    <td>${num(e.meta)}</td>
  </tr>`;
}

function valueHead() {
  return `<tr>
    <th data-key="name">Model</th>
    <th>Badge</th>
    <th data-key="coding_index">Coding idx</th>
    <th data-key="cost_task">$/task</th>
    <th data-key="price_mtok">$/Mtok</th>
    <th data-key="_ratio">idx / $</th>
    <th data-key="meta">Meta</th>
  </tr>`;
}

function changesRow(c) {
  const ev = c.event === "new" ? '<span class="badge new">NEW</span>' : c.event === "removed" ? `<span class="badge est">removed</span>` : `<span class="badge src">updated</span>`;
  return `<tr>
    <td>${esc(c.ts)}</td>
    <td>${esc(c.source)}</td>
    <td>${ev}</td>
    <td class="model-cell">${esc(c.name)}</td>
    <td>${esc(c.detail || "")}</td>
  </tr>`;
}

function sourcesRow(s) {
  const cls = s.last_error ? "err" : s.state === "paused" ? "paused" : s.state === "ok" ? "ok" : "muted";
  return `<tr>
    <td>${esc(s.name)}</td>
    <td class="${cls}">${esc(s.state)}</td>
    <td>${esc(s.last_ok || "never")}</td>
    <td>${s.row_count ?? "&mdash;"}</td>
    <td>${s.consecutive_errors || 0}</td>
    <td class="model-cell">${esc(s.last_error || "")}</td>
  </tr>`;
}

function renderTable(view, rows, headHtml, rowFn, maxVal) {
  const tbl = $(`#tbl-${view}`);
  let body = headHtml;
  const sortKey = state.sort.key;
  const dir = state.sort.dir;
  const sorted = [...rows];
  if (sortKey) {
    sorted.sort((a, b) => {
      let va = a[sortKey], vb = b[sortKey];
      if (sortKey === "_ratio") {
        va = a.coding_index / (a.cost_task ?? a.price_mtok ?? Infinity);
        vb = b.coding_index / (b.cost_task ?? b.price_mtok ?? Infinity);
      }
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === "string") return va.localeCompare(vb) * dir;
      return (va - vb) * dir;
    });
  }
  body += sorted.map((r) => rowFn(r, maxVal)).join("");
  tbl.innerHTML = body;
  tbl.querySelectorAll("th[data-key]").forEach((th) => {
    if (th.dataset.key === sortKey) th.classList.add(dir === -1 ? "sorted-desc" : "sorted-asc");
    th.onclick = () => {
      const key = th.dataset.key;
      if (state.sort.key === key) state.sort.dir *= -1;
      else state.sort = { key, dir: -1 };
      renderCurrent();
    };
  });
}

function renderCurrent() {
  const d = state.data;
  const maxCoding = Math.max(1, ...(d.coding || []).map((e) => e.coding_index || 0));
  renderTable("meta", d.meta || [], metaHead(), metaRow);
  renderTable("coding", d.coding || [], codingHead(), (e, m) => codingRow(e, maxCoding || m));
  renderTable("est", d.est || [], estHead(), estRow);
  renderTable("value", d.value || [], valueHead(), valueRow);
  renderTable("changes", d.changes || [], `<tr><th data-key="ts">When</th><th data-key="source">Source</th><th>Event</th><th data-key="name">Model</th><th>Detail</th></tr>`, changesRow);
  renderTable("sources", d.sources || [], `<tr><th data-key="name">Source</th><th data-key="state">State</th><th>Last ok</th><th>Rows</th><th>Errors</th><th>Error</th></tr>`, sourcesRow);
}

async function loadData() {
  try {
    const statusRes = await fetch("/api/status");
    if (!statusRes.ok) throw new Error("no api");
    const [meta, coding, est, value, changes, status] = await Promise.all([
      fetch("/api/views/meta").then((r) => r.json()),
      fetch("/api/views/coding").then((r) => r.json()),
      fetch("/api/views/est").then((r) => r.json()),
      fetch("/api/views/value").then((r) => r.json()),
      fetch("/api/changes").then((r) => r.json()),
      statusRes.json(),
    ]);
    state.data = {
      meta, coding, est, value, changes,
      sources: (status.sources || []).map((s) => {
        const sched = (status.scheduler || {})[s.source] || {};
        return { ...s, state: sched.state || (s.ok_count > 0 ? "ok" : "pending"), last_error: sched.error, consecutive_errors: sched.consecutive_errors };
      }),
    };
    if (status.latest_ts) $("#last-update").textContent = `last computed: ${status.latest_ts}`;
    renderCurrent();
  } catch {
    await loadStaticData();
  }
}

async function loadStaticData() {
  const d = await fetch("data.json", { cache: "no-store" }).then((r) => r.json());
  state.data = {
    meta: d.meta || [],
    coding: d.coding || [],
    est: d.est || [],
    value: d.value || [],
    changes: d.changes || [],
    sources: d.sources || [],
  };
  $("#refresh-btn").style.display = "none";
  if (d.status && d.status.latest_ts) $("#last-update").textContent = `last update: ${d.status.latest_ts}`;
  renderCurrent();
}

$("#tabs").addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-view]");
  if (!btn) return;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b === btn));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${btn.dataset.view}`));
});

$("#refresh-btn").addEventListener("click", async () => {
  const btn = $("#refresh-btn");
  btn.disabled = true;
  btn.textContent = "Refreshing\u2026";
  try {
    const res = await fetch("/api/refresh", { method: "POST" }).then((r) => r.json());
    if (!res.ok) {
      toast(res.msg || "refresh failed");
    } else {
      const failed = Object.keys(res.errors || {});
      toast(failed.length ? `Refresh done - failed: ${failed.join(", ")}` : `Refresh done - ${res.n_entities} entities`);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Refresh now";
    await loadData();
  }
});

function toast(msg) {
  const t = $("#toast") || Object.assign(document.createElement("div"), { id: "toast" });
  if (!$("#toast")) document.body.appendChild(t);
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.style.display = "none"), 6000);
}

loadData();
setInterval(loadData, 120000);