const $ = (selector, root = document) => root.querySelector(selector);
const state = {
  data: { meta: [], coding: [], est: [], value: [], changes: [], sources: [] },
  view: "overview",
  query: "",
  filter: "all",
  sort: "meta",
  staticMode: false,
};

const VIEW_META = {
  overview: { kicker: "Signal desk / overview", label: "Overview" },
  meta: { kicker: "Signal desk / composite", label: "Meta ranking" },
  coding: { kicker: "Signal desk / measured", label: "Coding agents" },
  est: { kicker: "Signal desk / forecast", label: "Estimates" },
  value: { kicker: "Signal desk / economics", label: "Value watch" },
  changes: { kicker: "Signal desk / movement", label: "Change log" },
  sources: { kicker: "Signal desk / inputs", label: "Sources" },
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function score(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const digits = Number(value) < 1 ? 3 : 2;
  return `$${Number(value).toFixed(digits)}`;
}

function shortName(name, limit = 58) {
  const text = String(name ?? "");
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function latestTimestamp() {
  return state.data.status?.latest_ts || state.data.sources?.find((source) => source.last_ok)?.last_ok || "Awaiting first scan";
}

function numberOfModels() {
  return state.data.meta?.length || state.data.coding?.length || 0;
}

function sourceCount() {
  return state.data.sources?.length || 0;
}

function badge(type, label) {
  return `<span class="badge ${type}">${esc(label)}</span>`;
}

function entityBadges(entity) {
  const d = entity.detail || {};
  const result = [entity.measured ? badge("measured", "Measured") : badge("est", "Estimated")];
  if (entity.is_new) result.push(badge("new", "New"));
  if (d.quirky_family) result.push(badge("warn", "Quirky family"));
  if (d.agrees === true) result.push(badge("agree", "Regressions agree"));
  if (d.agrees === false) result.push(badge("warn", "Needs caution"));
  return result.join("");
}

function getComponent(entity, category) {
  return Number(entity.components?.[category]?.value || 0);
}

function costLabel(entity) {
  if (entity.cost_task !== null && entity.cost_task !== undefined) return `${money(entity.cost_task)} / task`;
  if (entity.price_mtok !== null && entity.price_mtok !== undefined) return `${money(entity.price_mtok)} / Mtok`;
  return "Price unavailable";
}

function scoreMeter(value, color = "") {
  const safe = Math.max(0, Math.min(100, Number(value || 0)));
  return `<span class="score-meter ${color}"><i style="width:${safe}%"></i></span>`;
}

function miniBars(entity) {
  return `<div class="mini-bars">
    <div class="mini-bar"><span>CODE</span><i style="--value:${Math.max(0, Math.min(100, entity.coding_index || 0))}%"></i></div>
    <div class="mini-bar intel"><span>IQ</span><i style="--value:${Math.max(0, Math.min(100, entity.intelligence || 0))}%"></i></div>
  </div>`;
}

function sourcePills(entity) {
  const sources = new Set();
  Object.values(entity.components || {}).forEach((component) => {
    (component.sources || []).forEach((item) => sources.add(item.source));
  });
  if (!sources.size) return `<span class="drawer-note">No secondary source match</span>`;
  return [...sources].map((source) => `<span class="source-pill">${esc(source)}</span>`).join("");
}

function findEntity(slug) {
  return Object.values(state.data).flatMap((value) => Array.isArray(value) ? value : []).find((entity) => entity.slug === slug);
}

function filteredRows(rows, mode = "meta") {
  let output = [...(rows || [])];
  if (state.query) {
    const query = state.query.toLowerCase();
    output = output.filter((entity) => String(entity.name || "").toLowerCase().includes(query));
  }
  if (state.filter === "measured") output = output.filter((entity) => entity.measured);
  if (state.filter === "estimated") output = output.filter((entity) => !entity.measured);
  const key = state.sort || (mode === "est" ? "coding_index" : "meta");
  output.sort((a, b) => {
    if (key === "ratio") {
      const ratioA = (a.coding_index || 0) / (a.cost_task || a.price_mtok || Infinity);
      const ratioB = (b.coding_index || 0) / (b.cost_task || b.price_mtok || Infinity);
      return ratioB - ratioA;
    }
    if (key === "name") return String(a.name).localeCompare(String(b.name));
    return Number(b[key] || 0) - Number(a[key] || 0);
  });
  return output;
}

function modelRow(entity, index, mode = "meta") {
  const isEstimate = !entity.measured;
  const scoreValue = mode === "coding" ? entity.coding_index : mode === "est" ? entity.coding_index : entity.meta;
  const band = entity.meta_min !== null && entity.meta_max !== null ? `${score(entity.meta_min, 1)}–${score(entity.meta_max, 1)}` : "No band";
  const sub = mode === "est"
    ? `Intelligence ${score(entity.intelligence, 1)} · ${entity.detail?.agrees === false ? "dual regression disagrees" : "dual regression check"}`
    : `${entity.n_sources || 0} source signals · ${costLabel(entity)}`;
  const scoreLabel = mode === "coding" || mode === "est" ? "coding index" : "meta score";
  return `<article class="rank-row reveal" data-slug="${esc(entity.slug)}" tabindex="0" role="button" aria-label="Open details for ${esc(entity.name)}">
    <span class="rank-number">${String(index + 1).padStart(2, "0")}</span>
    <div class="rank-model">
      <strong>${esc(shortName(entity.name))}</strong>
      <small>${esc(sub)}</small>
      <div class="row-badges">${entityBadges(entity)}</div>
    </div>
    <div class="rank-score ${isEstimate ? "estimated" : ""}">${score(scoreValue)}<small>${scoreLabel}</small></div>
    ${mode === "est" ? `<div class="confidence"><b>±${score(entity.detail?.band, 2)}</b>${entity.detail?.extrapolated ? "extrapolated" : band}</div>` : `<div class="confidence"><b>${band}</b>confidence band</div>`}
    ${miniBars(entity)}
    <div class="rank-cost">${esc(costLabel(entity))}<small>${entity.price_mtok ? "blended price" : "benchmark cost"}</small></div>
    <div class="rank-sources">${entity.n_sources || 0}<small>signals</small></div>
    <div class="rank-arrow" aria-hidden="true">↗</div>
  </article>`;
}

function pageIntro(kicker, title, description, count) {
  return `<div class="view-intro reveal"><div><span class="eyebrow">${esc(kicker)}</span><h1 class="view-title">${title}</h1><p class="view-description">${esc(description)}</p></div><div class="view-count">${esc(count)}<br><span>records in current snapshot</span></div></div>`;
}

function toolbar() {
  return `<div class="toolbar reveal">
    <label class="search-wrap"><span>⌕</span><input id="model-search" type="search" placeholder="Search model or family" value="${esc(state.query)}" aria-label="Search models"></label>
    <div class="filter-group" role="group" aria-label="Filter model type">
      <button class="filter-button ${state.filter === "all" ? "active" : ""}" data-filter="all">All</button>
      <button class="filter-button ${state.filter === "measured" ? "active" : ""}" data-filter="measured">Measured</button>
      <button class="filter-button ${state.filter === "estimated" ? "active" : ""}" data-filter="estimated">Estimated</button>
    </div>
    <select class="sort-select" id="sort-select" aria-label="Sort models">
      <option value="meta" ${state.sort === "meta" ? "selected" : ""}>Sort: meta score</option>
      <option value="coding_index" ${state.sort === "coding_index" ? "selected" : ""}>Sort: coding index</option>
      <option value="intelligence" ${state.sort === "intelligence" ? "selected" : ""}>Sort: intelligence</option>
      <option value="ratio" ${state.sort === "ratio" ? "selected" : ""}>Sort: score / $</option>
      <option value="name" ${state.sort === "name" ? "selected" : ""}>Sort: name</option>
    </select>
  </div>`;
}

function renderOverview() {
  const meta = state.data.meta || [];
  const coding = state.data.coding || [];
  const est = state.data.est || [];
  const value = state.data.value || [];
  const top = meta[0] || {};
  const measuredLeader = coding[0] || top;
  const estimateLeader = est[0] || {};
  const valueLeader = value[0] || {};
  const changes = state.data.changes || [];
  const anatomy = [
    ["Coding agent", top.coding_index, ""],
    ["Intelligence", top.intelligence, "violet"],
    ["Code correctness", getComponent(top, "code_correctness"), "orange"],
    ["Human preference", getComponent(top, "human_pref"), "cyan"],
    ["Agentic / terminal", getComponent(top, "agentic"), ""],
  ];
  return `<section class="hero reveal">
    <div class="hero-copy"><span class="eyebrow">Live frontier index / ${numberOfModels()} models tracked</span><h1>Find the signal<br><em>inside the noise.</em></h1><p class="hero-description">A private observatory for model capability, agent performance, cost, and confidence. One score is useful. The trail behind it is better.</p></div>
    <div class="hero-art" aria-hidden="true"><div class="orbit"><span class="orbit-dot"></span><span class="orbit-label">LIVE / MULTI-SOURCE</span><div class="orbit-core">SCORE<br>FIELD</div></div><div class="hero-score-card"><span class="hero-score-label">Current composite leader</span><div class="hero-score">${score(top.meta)}<sup>/100</sup></div><div class="hero-model">${esc(top.name || "No score yet")}</div><div class="hero-model-meta">${top.measured ? "MEASURED SIGNAL" : "ESTIMATED SIGNAL"} · ${top.n_sources || 0} source signals</div></div></div>
  </section>
  <section class="stats-strip reveal">
    <div class="stat"><div class="stat-value">${numberOfModels()}</div><div class="stat-label">Models tracked</div><div class="stat-detail">${coding.length} measured / ${est.length} estimated</div></div>
    <div class="stat"><div class="stat-value">${sourceCount()}</div><div class="stat-label">Live sources</div><div class="stat-detail">AA, arenas, coding evals</div></div>
    <div class="stat"><div class="stat-value">${score(measuredLeader.coding_index, 1)}</div><div class="stat-label">Measured coding lead</div><div class="stat-detail">${esc(shortName(measuredLeader.name, 28))}</div></div>
    <div class="stat"><div class="stat-value">${score(estimateLeader.coding_index, 1)}</div><div class="stat-label">Top EST candidate</div><div class="stat-detail">${esc(shortName(estimateLeader.name, 28))}</div></div>
  </section>
  <div class="section-head reveal"><div><span class="section-label">01 / Leaderboard pulse</span><h2>Who is moving<br>the ceiling?</h2></div><span class="section-note">Click any model to open its full signal anatomy.</span></div>
  <section class="overview-grid">
    <div class="panel reveal"><div class="panel-heading"><h3>Composite ranking</h3><span>top 05 / current snapshot</span></div><div class="spotlight-list">${meta.slice(0, 5).map((entity, index) => `<div class="spotlight-row" data-slug="${esc(entity.slug)}" tabindex="0" role="button"><span class="spotlight-rank">${String(index + 1).padStart(2, "0")}</span><div><div class="spotlight-name">${esc(entity.name)}</div><div class="spotlight-sub">${entity.measured ? "MEASURED" : "ESTIMATED"} · ${entity.n_sources || 0} source signals</div></div><div class="spotlight-score">${score(entity.meta)}<small>${entity.meta_min !== null ? `${score(entity.meta_min, 1)}–${score(entity.meta_max, 1)}` : "no band"}</small></div><div class="score-meter"><i style="width:${Math.min(100, entity.meta || 0)}%"></i></div></div>`).join("")}</div></div>
    <div class="insight-stack">
      <div class="insight-card acid reveal"><span class="insight-label">Best measured workhorse</span><div class="insight-value">${esc(shortName(measuredLeader.name, 34))}</div><div class="insight-number">${score(measuredLeader.coding_index)}</div><div class="insight-detail">${esc(costLabel(measuredLeader))} · coding agent index</div><span class="insight-arrow">↗</span></div>
      <div class="insight-card orange reveal"><span class="insight-label">Top forecast</span><div class="insight-value">${esc(shortName(estimateLeader.name, 34))}</div><div class="insight-number">${score(estimateLeader.coding_index)}</div><div class="insight-detail">±${score(estimateLeader.detail?.band, 2)} estimate · ${estimateLeader.detail?.agrees === false ? "needs caution" : "dual regression agrees"}</div><span class="insight-arrow">↗</span></div>
      <div class="insight-card violet reveal"><span class="insight-label">Raw value ratio</span><div class="insight-value">${esc(shortName(valueLeader.name, 34))}</div><div class="insight-number">${score((valueLeader.coding_index || 0) / (valueLeader.cost_task || valueLeader.price_mtok || 1), 1)}×</div><div class="insight-detail">${esc(costLabel(valueLeader))} · score per dollar</div><span class="insight-arrow">↗</span></div>
    </div>
  </section>
  <section class="panel anatomy-panel reveal"><div class="panel-heading"><h3>Score anatomy / current leader</h3><span>${esc(shortName(top.name, 42))}</span></div><div class="anatomy-layout"><div class="anatomy-score"><span class="eyebrow">Composite score</span><div class="anatomy-score-value">${score(top.meta)}<span>/100</span></div><div class="anatomy-name">${esc(top.name || "—")}</div><div class="row-badges">${entityBadges(top)}</div></div><div class="anatomy-bars">${anatomy.map(([label, value, color]) => `<div class="metric-line"><span class="metric-label">${label}</span>${scoreMeter(value, color)}<span class="metric-value">${score(value, 1)}</span></div>`).join("")}</div></div></section>
  <section class="section-head reveal" style="margin-top:58px"><div><span class="section-label">02 / Fresh movement</span><h2>What changed<br>since last scan?</h2></div><span class="section-note">${changes.length ? `${changes.length} changes recorded` : "No new changes in the latest snapshot"}</span></section>
  ${renderTimeline(changes.slice(0, 5))}`;
}

function renderRanking(view) {
  const config = {
    meta: ["Meta ranking", "The composite field", "The weighted view across coding skill, intelligence, correctness, preference, and agentic performance."],
    coding: ["Measured coding agents", "The workbench", "Artificial Analysis Coding Agent Index, with cost and wall-time context. Measured entries only."],
    est: ["Estimated frontier", "Before the benchmark", "Models with intelligence data but no measured coding-agent entry yet. Treat the band as part of the score."],
  }[view];
  const rows = filteredRows(state.data[view], view);
  return `${pageIntro(config[0], config[1], config[2], rows.length)}${toolbar()}<section class="rank-list">${rows.length ? rows.slice(0, 200).map((entity, index) => modelRow(entity, index, view)).join("") : `<div class="empty-state"><strong>No signal here.</strong>Try a different search or filter.</div>`}</section>`;
}

function renderValue() {
  const rows = filteredRows(state.data.value, "value");
  const featured = rows[0] || {};
  return `${pageIntro("Economics / score against cost", "Value watch", "A sharper way to compare capability and spend. The raw ratio favors cheap models; use the task cost and meta score together.", rows.length)}
    <section class="value-feature reveal"><div><span class="feature-kicker">Raw ratio leader</span><h3>${esc(featured.name || "No value data yet")}</h3><p>${score(featured.coding_index)} coding index at ${esc(costLabel(featured))}. This is the cheapest signal in the current snapshot, not a universal winner.</p></div><div class="value-feature-score"><strong>${score((featured.coding_index || 0) / (featured.cost_task || featured.price_mtok || 1), 1)}×</strong><span>INDEX / DOLLAR</span></div></section>
    ${toolbar()}<section class="rank-list">${rows.length ? rows.slice(0, 200).map((entity, index) => modelRow(entity, index, "value")).join("") : `<div class="empty-state"><strong>No prices found.</strong>Try another view.</div>`}</section>`;
}

function renderTimeline(changes) {
  if (!changes.length) return `<div class="empty-state reveal"><strong>Quiet field.</strong>No source has changed since the previous snapshot.</div>`;
  return `<section class="panel timeline reveal">${changes.map((change) => `<div class="timeline-item"><span class="timeline-dot"></span><span class="timeline-date">${esc(String(change.ts || "").replace("T", " ").replace("Z", ""))}</span><div><div class="timeline-title">${esc(change.name)}</div><div class="timeline-detail">${esc(change.detail || "")}</div></div><span class="timeline-source">${esc(change.event)} / ${esc(change.source)}</span></div>`).join("")}</section>`;
}

function renderChanges() {
  const changes = state.data.changes || [];
  return `${pageIntro("Movement / source diffs", "Change log", "A quiet record of what entered, left, or shifted between snapshots. New models are the event worth watching.", changes.length)}${renderTimeline(changes)}`;
}

function renderSources() {
  const sources = state.data.sources || [];
  return `${pageIntro("Inputs / source health", "Source room", "Every composite score starts here. Sources are cached, diffed, and paused after repeated failures rather than silently trusted.", sources.length)}<section class="source-grid">${sources.map((source) => `<article class="source-card reveal"><div class="source-card-top"><span class="source-name">${esc(source.source || source.name)}</span><span class="source-state ${source.state === "ok" ? "" : "pending"}">${esc(source.state || "pending")}</span></div><div class="source-meta"><span>LAST OK</span><span>${esc(source.last_ok || "never")}</span></div><div class="source-line"><i></i></div></article>`).join("")}</section>`;
}

function renderView() {
  const main = $("#app-main");
  const output = state.view === "overview" ? renderOverview() : state.view === "value" ? renderValue() : state.view === "changes" ? renderChanges() : state.view === "sources" ? renderSources() : renderRanking(state.view);
  main.innerHTML = output;
  wireViewEvents();
  requestAnimationFrame(() => document.querySelectorAll(".reveal").forEach((element) => element.classList.add("revealed")));
  updateShell();
}

function updateShell() {
  const meta = VIEW_META[state.view];
  $("#section-kicker").textContent = meta.kicker;
  $("#last-update").textContent = state.staticMode ? `last update / ${latestTimestamp()}` : `last scan / ${latestTimestamp()}`;
  $("#source-summary").textContent = `${sourceCount()} sources · ${numberOfModels()} models in field`;
  $("#sync-label").textContent = state.staticMode ? "Static index live" : "Live index connected";
  document.querySelectorAll(".nav-item").forEach((item) => {
    const active = item.dataset.view === state.view;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
}

function wireViewEvents() {
  document.querySelectorAll("[data-slug]").forEach((element) => {
    element.addEventListener("click", () => openDrawer(element.dataset.slug));
    element.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openDrawer(element.dataset.slug); } });
  });
  const search = $("#model-search");
  if (search) {
    search.addEventListener("input", (event) => { state.query = event.target.value; renderView(); });
    search.addEventListener("keydown", (event) => event.stopPropagation());
  }
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.filter; renderView(); }));
  const sort = $("#sort-select");
  if (sort) sort.addEventListener("change", (event) => { state.sort = event.target.value; renderView(); });
}

function openDrawer(slug) {
  const entity = findEntity(slug);
  if (!entity) return;
  const drawer = $("#detail-drawer");
  const d = entity.detail || {};
  const categories = [["Coding agent", entity.coding_index, ""], ["Intelligence", entity.intelligence, "violet"], ["Code correctness", getComponent(entity, "code_correctness"), "orange"], ["Human preference", getComponent(entity, "human_pref"), "cyan"], ["Agentic / terminal", getComponent(entity, "agentic"), ""]];
  $("#drawer-content").innerHTML = `<span class="drawer-kicker">${entity.measured ? "Measured signal" : "Forecast signal"} / ${entity.n_sources || 0} sources</span><h2 class="drawer-title" id="drawer-title">${esc(entity.name)}</h2><p class="drawer-subtitle">${esc(entity.harness || entity.model_name || "Cross-source identity match")}</p><div class="drawer-scoreline"><div class="drawer-score">${score(entity.meta)}<span>COMPOSITE / 100${entity.meta_min !== null ? ` · ${score(entity.meta_min, 1)}–${score(entity.meta_max, 1)}` : ""}</span></div><div class="drawer-stats"><div class="drawer-stat"><b>${score(entity.coding_index, 1)}</b><small>coding index</small></div><div class="drawer-stat"><b>${money(entity.cost_task)}</b><small>task cost</small></div><div class="drawer-stat"><b>${money(entity.price_mtok)}</b><small>$/mtok</small></div></div></div><section class="drawer-section"><h4>Signal anatomy</h4>${categories.map(([label, value, color]) => `<div class="component-row"><label>${label}</label>${scoreMeter(value, color)}<strong>${score(value, 1)}</strong></div>`).join("")}</section><section class="drawer-section"><h4>Sources attached</h4><div class="source-pills">${sourcePills(entity)}</div></section>${!entity.measured ? `<section class="drawer-section"><h4>Estimate notes</h4>${d.quirky_family ? `<div class="drawer-warning">Quirky family flag. This model family has shown a systematic coding gap against general intelligence.</div>` : ""}<p class="drawer-note">Intelligence regression: ${score(d.est_from_intelligence, 3)} · coding-index cross-check: ${score(d.est_from_coding_index, 3)} · band ±${score(d.band, 2)} · ${d.agrees === false ? "the two regressions disagree" : "the two regressions agree"}.</p></section>` : ""}`;
  $("#drawer-backdrop").hidden = false;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  drawer.focus();
}

function closeDrawer() {
  const drawer = $("#detail-drawer");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  setTimeout(() => { $("#drawer-backdrop").hidden = true; }, 250);
}

async function loadData() {
  try {
    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) throw new Error("Static mode");
    const [meta, coding, est, value, changes, status] = await Promise.all([
      fetch("/api/views/meta").then((response) => response.json()),
      fetch("/api/views/coding").then((response) => response.json()),
      fetch("/api/views/est").then((response) => response.json()),
      fetch("/api/views/value").then((response) => response.json()),
      fetch("/api/changes").then((response) => response.json()),
      statusResponse.json(),
    ]);
    state.data = { meta, coding, est, value, changes, sources: status.sources || [], status };
  } catch {
    state.staticMode = true;
    state.data = await fetch("data.json", { cache: "no-store" }).then((response) => response.json());
    $("#refresh-btn").style.display = "none";
  }
  renderView();
}

function setView(view) {
  state.view = view;
  state.query = "";
  state.filter = "all";
  state.sort = view === "est" || view === "coding" ? "coding_index" : view === "value" ? "ratio" : "meta";
  renderView();
  $("#app-main").focus({ preventScroll: true });
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) setView(nav.dataset.view);
  if (event.target.id === "drawer-backdrop" || event.target.closest("#drawer-close")) closeDrawer();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  if (event.key.toLowerCase() === "r" && !event.target.matches("input, select, textarea") && !state.staticMode) $("#refresh-btn")?.click();
});

$("#refresh-btn").addEventListener("click", async () => {
  const button = $("#refresh-btn");
  button.disabled = true;
  button.querySelector("span").textContent = "Scanning…";
  try {
    const response = await fetch("/api/refresh", { method: "POST" });
    const result = await response.json();
    toast(result.ok ? `Scan complete · ${result.n_entities} entities refreshed` : result.msg || "Scan failed");
    await loadData();
  } catch { toast("The local scanner did not respond."); }
  button.disabled = false;
  button.querySelector("span").textContent = "Refresh scan";
});

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.style.display = "block";
  clearTimeout(element._timer);
  element._timer = setTimeout(() => { element.style.display = "none"; }, 5000);
}

$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-backdrop").addEventListener("click", closeDrawer);
loadData();
setInterval(loadData, 120000);
