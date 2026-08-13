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
  overview: { label: "Overview" },
  meta: { label: "All models" },
  coding: { label: "Coding scores" },
  est: { label: "Predictions" },
  value: { label: "Best value" },
  changes: { label: "What changed" },
  sources: { label: "Data sources" },
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function score(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? "-" : Number(value).toFixed(digits);
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `$${Number(value).toFixed(Number(value) < 1 ? 3 : 2)}`;
}

function shortName(value, limit = 58) {
  const text = String(value ?? "");
  return text.length > limit ? `${text.slice(0, limit - 1)}...` : text;
}

function badge(type, label) {
  return `<span class="badge ${type}">${esc(label)}</span>`;
}

function entityBadges(entity) {
  const detail = entity.detail || {};
  const output = [entity.measured ? badge("measured", "Measured") : badge("est", "Predicted")];
  if (entity.is_new) output.push(badge("new", "New"));
  if (detail.quirky_family) output.push(badge("warn", "Family caution"));
  if (detail.agrees === true) output.push(badge("agree", "Checks agree"));
  if (detail.agrees === false) output.push(badge("warn", "Check scores"));
  return output.join("");
}

function componentValue(entity, category) {
  return Number(entity.components?.[category]?.value || 0);
}

function costLabel(entity) {
  if (entity.cost_task !== null && entity.cost_task !== undefined) return `${money(entity.cost_task)} / task`;
  if (entity.price_mtok !== null && entity.price_mtok !== undefined) return `${money(entity.price_mtok)} / Mtok`;
  return "Price unavailable";
}

function meter(value, color = "") {
  const safe = Math.max(0, Math.min(100, Number(value || 0)));
  return `<span class="score-meter ${color}"><i style="width:${safe}%"></i></span>`;
}

function miniBars(entity) {
  return `<div class="mini-bars"><div class="mini-bar"><span>Coding</span><i style="--value:${Math.max(0, Math.min(100, entity.coding_index || 0))}%"></i></div><div class="mini-bar intel"><span>General</span><i style="--value:${Math.max(0, Math.min(100, entity.intelligence || 0))}%"></i></div></div>`;
}

function sourcePills(entity) {
  const sources = new Set();
  Object.values(entity.components || {}).forEach((component) => (component.sources || []).forEach((item) => sources.add(item.source)));
  if (!sources.size) return `<span class="drawer-note">No extra comparisons yet.</span>`;
  return [...sources].map((source) => `<span class="source-pill">${esc(source)}</span>`).join("");
}

function findEntity(slug) {
  return Object.values(state.data).flatMap((value) => Array.isArray(value) ? value : []).find((entity) => entity.slug === slug);
}

function filteredRows(rows) {
  let output = [...(rows || [])];
  if (state.query) {
    const query = state.query.toLowerCase();
    output = output.filter((entity) => String(entity.name || "").toLowerCase().includes(query));
  }
  if (state.filter === "measured") output = output.filter((entity) => entity.measured);
  if (state.filter === "estimated") output = output.filter((entity) => !entity.measured);
  output.sort((a, b) => {
    if (state.sort === "ratio") return ((b.coding_index || 0) / (b.cost_task || b.price_mtok || Infinity)) - ((a.coding_index || 0) / (a.cost_task || a.price_mtok || Infinity));
    if (state.sort === "name") return String(a.name).localeCompare(String(b.name));
    return Number(b[state.sort] || 0) - Number(a[state.sort] || 0);
  });
  return output;
}

function modelRow(entity, index, mode = "meta") {
  const scoreValue = mode === "coding" || mode === "est" ? entity.coding_index : entity.meta;
  const scoreLabel = mode === "coding" ? "coding score" : mode === "est" ? "prediction" : "overall score";
  const range = entity.meta_min !== null && entity.meta_max !== null ? `${score(entity.meta_min, 1)} - ${score(entity.meta_max, 1)}` : "No range";
  const description = mode === "est"
    ? `Predicted coding score - ${entity.detail?.agrees === false ? "check this one carefully" : "both checks agree"}`
    : `${entity.n_sources || 0} comparisons - ${costLabel(entity)}`;
  return `<article class="rank-row reveal" data-slug="${esc(entity.slug)}" tabindex="0" role="button" aria-label="Open details for ${esc(entity.name)}">
    <span class="rank-number">${String(index + 1).padStart(2, "0")}</span>
    <div class="rank-model"><strong>${esc(shortName(entity.name))}</strong><small>${esc(description)}</small><div class="row-badges">${entityBadges(entity)}</div></div>
    <div class="rank-score ${entity.measured ? "" : "estimated"}">${score(scoreValue)}<small>${scoreLabel}</small></div>
    ${mode === "est" ? `<div class="confidence"><b>+/-${score(entity.detail?.band, 2)}</b>${entity.detail?.extrapolated ? "outside usual range" : "expected range"}</div>` : `<div class="confidence"><b>${range}</b>likely range</div>`}
    ${miniBars(entity)}
    <div class="rank-cost">${esc(costLabel(entity))}<small>${entity.price_mtok ? "model price" : "test cost"}</small></div>
    <div class="rank-sources">${entity.n_sources || 0}<small>comparisons</small></div>
    <div class="rank-arrow" aria-hidden="true">></div>
  </article>`;
}

function pageIntro(label, title, description, count) {
  return `<div class="view-intro reveal"><div><span class="eyebrow">${esc(label)}</span><h1 class="view-title">${title}</h1><p class="view-description">${esc(description)}</p></div><div class="view-count">${esc(count)}<br><span>models in this view</span></div></div>`;
}

function toolbar() {
  return `<div class="toolbar reveal"><label class="search-wrap"><span>⌕</span><input id="model-search" type="search" placeholder="Search models" value="${esc(state.query)}" aria-label="Search models"></label><div class="filter-group" role="group" aria-label="Filter models"><button class="filter-button ${state.filter === "all" ? "active" : ""}" data-filter="all">All</button><button class="filter-button ${state.filter === "measured" ? "active" : ""}" data-filter="measured">Measured</button><button class="filter-button ${state.filter === "estimated" ? "active" : ""}" data-filter="estimated">Predicted</button></div><select class="sort-select" id="sort-select" aria-label="Sort models"><option value="meta" ${state.sort === "meta" ? "selected" : ""}>Sort by overall score</option><option value="coding_index" ${state.sort === "coding_index" ? "selected" : ""}>Sort by coding score</option><option value="intelligence" ${state.sort === "intelligence" ? "selected" : ""}>Sort by general score</option><option value="ratio" ${state.sort === "ratio" ? "selected" : ""}>Sort by value</option><option value="name" ${state.sort === "name" ? "selected" : ""}>Sort by name</option></select></div>`;
}

function renderOverview() {
  const meta = state.data.meta || [];
  const coding = state.data.coding || [];
  const estimates = state.data.est || [];
  const value = state.data.value || [];
  const top = meta[0] || {};
  const measuredLeader = coding[0] || top;
  const predictionLeader = estimates[0] || {};
  const valueLeader = value[0] || {};
  const changes = state.data.changes || [];
  const anatomy = [["Coding", top.coding_index, ""], ["General score", top.intelligence, "violet"], ["Code tests", componentValue(top, "code_correctness"), "orange"], ["People's choice", componentValue(top, "human_pref"), "cyan"], ["Agent tasks", componentValue(top, "agentic"), ""]];
  return `<section class="hero reveal"><div class="hero-copy"><span class="eyebrow">${meta.length} models compared</span><h1>The model landscape,<br><em>made simple.</em></h1><p class="hero-description">See which models lead, which ones are still being tested, and what you get for the money. The data updates automatically.</p></div><div class="hero-art" aria-hidden="true"><div class="orbit"><span class="orbit-dot"></span><span class="orbit-label">UPDATED AUTOMATICALLY</span><div class="orbit-core">COMPARE<br>MODELS</div></div><div class="hero-score-card"><span class="hero-score-label">Top model today</span><div class="hero-score">${score(top.meta)}<sup>/100</sup></div><div class="hero-model">${esc(top.name || "No score yet")}</div><div class="hero-model-meta">${top.measured ? "Measured score" : "Predicted score"} · ${top.n_sources || 0} comparisons</div></div></div></section><section class="stats-strip reveal"><div class="stat"><div class="stat-value">${meta.length}</div><div class="stat-label">Models compared</div><div class="stat-detail">${coding.length} measured / ${estimates.length} predicted</div></div><div class="stat"><div class="stat-value">${state.data.sources?.length || 0}</div><div class="stat-label">Data sources</div><div class="stat-detail">Scores checked regularly</div></div><div class="stat"><div class="stat-value">${score(measuredLeader.coding_index, 1)}</div><div class="stat-label">Best measured coding</div><div class="stat-detail">${esc(shortName(measuredLeader.name, 28))}</div></div><div class="stat"><div class="stat-value">${score(predictionLeader.coding_index, 1)}</div><div class="stat-label">Best prediction</div><div class="stat-detail">${esc(shortName(predictionLeader.name, 28))}</div></div></section><div class="section-head reveal"><div><span class="section-label">Top models</span><h2>The strongest scores<br>right now.</h2></div><span class="section-note">Select a model to see how its score is built.</span></div><section class="overview-grid"><div class="panel reveal"><div class="panel-heading"><h3>Overall ranking</h3><span>Top 5</span></div><div class="spotlight-list">${meta.slice(0, 5).map((entity, index) => `<div class="spotlight-row" data-slug="${esc(entity.slug)}" tabindex="0" role="button"><span class="spotlight-rank">${String(index + 1).padStart(2, "0")}</span><div><div class="spotlight-name">${esc(entity.name)}</div><div class="spotlight-sub">${entity.measured ? "Measured" : "Predicted"} · ${entity.n_sources || 0} comparisons</div></div><div class="spotlight-score">${score(entity.meta)}<small>${entity.meta_min !== null ? `${score(entity.meta_min, 1)} - ${score(entity.meta_max, 1)}` : "no range"}</small></div><div class="score-meter"><i style="width:${Math.min(100, entity.meta || 0)}%"></i></div></div>`).join("")}</div></div><div class="insight-stack"><div class="insight-card acid reveal"><span class="insight-label">Best measured coding score</span><div class="insight-value">${esc(shortName(measuredLeader.name, 34))}</div><div class="insight-number">${score(measuredLeader.coding_index)}</div><div class="insight-detail">${esc(costLabel(measuredLeader))}</div><span class="insight-arrow">></span></div><div class="insight-card orange reveal"><span class="insight-label">Highest prediction</span><div class="insight-value">${esc(shortName(predictionLeader.name, 34))}</div><div class="insight-number">${score(predictionLeader.coding_index)}</div><div class="insight-detail">+/-${score(predictionLeader.detail?.band, 2)} · ${predictionLeader.detail?.agrees === false ? "check before trusting" : "both checks agree"}</div><span class="insight-arrow">></span></div><div class="insight-card violet reveal"><span class="insight-label">Best score for the money</span><div class="insight-value">${esc(shortName(valueLeader.name, 34))}</div><div class="insight-number">${score((valueLeader.coding_index || 0) / (valueLeader.cost_task || valueLeader.price_mtok || 1), 1)}x</div><div class="insight-detail">${esc(costLabel(valueLeader))} · raw value ratio</div><span class="insight-arrow">></span></div></div></section><section class="panel anatomy-panel reveal"><div class="panel-heading"><h3>Why this model is first</h3><span>${esc(shortName(top.name, 42))}</span></div><div class="anatomy-layout"><div class="anatomy-score"><span class="eyebrow">Overall score</span><div class="anatomy-score-value">${score(top.meta)}<span>/100</span></div><div class="anatomy-name">${esc(top.name || "-")}</div><div class="row-badges">${entityBadges(top)}</div></div><div class="anatomy-bars">${anatomy.map(([label, value, color]) => `<div class="metric-line"><span class="metric-label">${label}</span>${meter(value, color)}<span class="metric-value">${score(value, 1)}</span></div>`).join("")}</div></div></section><section class="section-head reveal" style="margin-top:58px"><div><span class="section-label">Latest updates</span><h2>What changed<br>recently?</h2></div><span class="section-note">${changes.length ? `${changes.length} changes recorded` : "No updates since the last check"}</span></section>${renderTimeline(changes.slice(0, 5))}`;
}

function renderRanking(view) {
  const config = { meta: ["All models", "Compare the leaders", "One clear score for each model, combining the latest performance, preference, and cost data."], coding: ["Coding scores", "The best at coding", "Measured results from the coding leaderboard, with price and task cost beside them."], est: ["Predictions", "Before the benchmark", "A useful early view of models that have not appeared on the coding leaderboard yet. Predictions include a range."] }[view];
  const rows = filteredRows(state.data[view]);
  return `${pageIntro(config[0], config[1], config[2], rows.length)}${toolbar()}<section class="rank-list">${rows.length ? rows.slice(0, 200).map((entity, index) => modelRow(entity, index, view)).join("") : `<div class="empty-state"><strong>No models found.</strong>Try a different search or filter.</div>`}</section>`;
}

function renderValue() {
  const rows = filteredRows(state.data.value);
  const featured = rows[0] || {};
  return `${pageIntro("Compare performance and price", "Best value", "A low price helps, but a strong score still has to come first. Use this view to find the best trade-off.", rows.length)}<section class="value-feature reveal"><div><span class="feature-kicker">Best score for the money</span><h3>${esc(featured.name || "No value data yet")}</h3><p>${score(featured.coding_index)} coding score at ${esc(costLabel(featured))}. This is the raw value leader in the current snapshot.</p></div><div class="value-feature-score"><strong>${score((featured.coding_index || 0) / (featured.cost_task || featured.price_mtok || 1), 1)}x</strong><span>SCORE / DOLLAR</span></div></section>${toolbar()}<section class="rank-list">${rows.length ? rows.slice(0, 200).map((entity, index) => modelRow(entity, index, "value")).join("") : `<div class="empty-state"><strong>No prices found.</strong>Try another view.</div>`}</section>`;
}

function renderTimeline(changes) {
  if (!changes.length) return `<div class="empty-state reveal"><strong>Nothing new yet.</strong>No source has changed since the previous check.</div>`;
  return `<section class="panel timeline reveal">${changes.map((change) => `<div class="timeline-item"><span class="timeline-dot"></span><span class="timeline-date">${esc(String(change.ts || "").replace("T", " ").replace("Z", ""))}</span><div><div class="timeline-title">${esc(change.name)}</div><div class="timeline-detail">${esc(change.detail || "")}</div></div><span class="timeline-source">${esc(change.event)} / ${esc(change.source)}</span></div>`).join("")}</section>`;
}

function renderChanges() {
  const changes = state.data.changes || [];
  return `${pageIntro("Recent updates", "What changed", "A simple history of new models, score changes, and leaderboard movement.", changes.length)}${renderTimeline(changes)}`;
}

function renderSources() {
  const sources = state.data.sources || [];
  return `${pageIntro("Where the numbers come from", "Data sources", "The tracker checks public leaderboards and keeps a history of what each one reports.", sources.length)}<section class="source-grid">${sources.map((source) => `<article class="source-card reveal"><div class="source-card-top"><span class="source-name">${esc(source.source || source.name)}</span><span class="source-state ${source.state === "ok" ? "" : "pending"}">${esc(source.state || "pending")}</span></div><div class="source-meta"><span>LAST CHECKED</span><span>${esc(source.last_ok || "never")}</span></div><div class="source-line"><i></i></div></article>`).join("")}</section>`;
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
  $("#section-kicker").textContent = VIEW_META[state.view].label;
  $("#last-update").textContent = state.staticMode ? `Last update: ${latestTimestamp()}` : `Last checked: ${latestTimestamp()}`;
  $("#source-summary").textContent = `${state.data.sources?.length || 0} sources · ${numberOfModels()} models`;
  $("#sync-label").textContent = state.staticMode ? "Latest data ready" : "Live data connected";
  document.querySelectorAll(".nav-item").forEach((item) => {
    const active = item.dataset.view === state.view;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
}

function wireViewEvents() {
  document.querySelectorAll("[data-slug]").forEach((element) => {
    element.addEventListener("click", () => openDrawer(element.dataset.slug));
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDrawer(element.dataset.slug);
      }
    });
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
  const detail = entity.detail || {};
  const categories = [["Coding", entity.coding_index, ""], ["General score", entity.intelligence, "violet"], ["Code tests", componentValue(entity, "code_correctness"), "orange"], ["People's choice", componentValue(entity, "human_pref"), "cyan"], ["Agent tasks", componentValue(entity, "agentic"), ""]];
  $("#drawer-content").innerHTML = `<span class="drawer-kicker">${entity.measured ? "Measured score" : "Prediction"} · ${entity.n_sources || 0} comparisons</span><h2 class="drawer-title" id="drawer-title">${esc(entity.name)}</h2><p class="drawer-subtitle">${esc(entity.harness || entity.model_name || "Compared across public leaderboards")}</p><div class="drawer-scoreline"><div class="drawer-score">${score(entity.meta)}<span>OVERALL SCORE / 100${entity.meta_min !== null ? ` · ${score(entity.meta_min, 1)} - ${score(entity.meta_max, 1)}` : ""}</span></div><div class="drawer-stats"><div class="drawer-stat"><b>${score(entity.coding_index, 1)}</b><small>coding score</small></div><div class="drawer-stat"><b>${money(entity.cost_task)}</b><small>cost per task</small></div><div class="drawer-stat"><b>${money(entity.price_mtok)}</b><small>per million tokens</small></div></div></div><section class="drawer-section"><h4>How this score is built</h4>${categories.map(([label, value, color]) => `<div class="component-row"><label>${label}</label>${meter(value, color)}<strong>${score(value, 1)}</strong></div>`).join("")}</section><section class="drawer-section"><h4>Compared with</h4><div class="source-pills">${sourcePills(entity)}</div></section>${!entity.measured ? `<section class="drawer-section"><h4>About this prediction</h4>${detail.quirky_family ? `<div class="drawer-warning">This model family has been less reliable at coding than its general score suggests.</div>` : ""}<p class="drawer-note">The two prediction checks are ${detail.agrees === false ? "not close, so treat this result carefully" : "close enough to support the estimate"}. The expected error range is +/-${score(detail.band, 2)}.</p></section>` : ""}`;
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
  const navigation = event.target.closest("[data-view]");
  if (navigation) setView(navigation.dataset.view);
  if (event.target.id === "drawer-backdrop" || event.target.closest("#drawer-close")) closeDrawer();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  if (event.key.toLowerCase() === "r" && !event.target.matches("input, select, textarea") && !state.staticMode) $("#refresh-btn")?.click();
});

$("#refresh-btn").addEventListener("click", async () => {
  const button = $("#refresh-btn");
  button.disabled = true;
  button.querySelector("span").textContent = "Checking...";
  try {
    const response = await fetch("/api/refresh", { method: "POST" });
    const result = await response.json();
    toast(result.ok ? `Data refreshed: ${result.n_entities} models` : result.msg || "The refresh failed.");
    await loadData();
  } catch {
    toast("The local tracker did not respond.");
  }
  button.disabled = false;
  button.querySelector("span").textContent = "Refresh data";
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
