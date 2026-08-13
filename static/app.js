const $ = (selector) => document.querySelector(selector);

const state = {
  coding: [],
  est: [],
  radar: { articles: [], new_models: [], candidates: [] },
  page: "leaderboard",
  slider: 50,
  staticMode: false,
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function num(value, digits = 1) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `$${Number(value).toFixed(Number(value) < 1 ? 3 : 2)}`;
}

function minutes(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "—";
  const mins = Math.round(Number(seconds) / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function isEstimated(model) {
  return !model.measured;
}

function allModels() {
  return [...state.coding, ...state.est];
}

function quality(model) {
  return Number(model.coding_index || 0);
}

function band(model) {
  const width = (model.detail?.band ?? 0.06) * 100;
  return [Math.max(0, quality(model) - width), Math.min(100, quality(model) + width)];
}

function sliderCost(model) {
  return model.price_mtok !== null && model.price_mtok !== undefined ? model.price_mtok : model.cost_task;
}

function costNorm(model) {
  const costs = allModels().map(sliderCost).filter((value) => value !== null && value !== undefined);
  if (costs.length < 2) return 0;
  const min = Math.min(...costs);
  const max = Math.max(...costs);
  const cost = sliderCost(model);
  if (cost === null || cost === undefined) return 0.5;
  return max === min ? 0 : (cost - min) / (max - min);
}

function blendedScore(model) {
  const weight = state.slider / 100;
  return weight * quality(model) + (1 - weight) * (1 - costNorm(model)) * 100;
}

function leanLabel() {
  if (state.slider >= 60) return "quality";
  if (state.slider <= 40) return "cost";
  return "a balance of both";
}

function badges(model) {
  const output = [];
  const detail = model.detail || {};
  if (isEstimated(model)) output.push('<span class="badge est" title="Predicted score: this model has not appeared on the coding benchmark yet">Estimated</span>');
  if (model.is_new) output.push('<span class="badge new">New</span>');
  if (isEstimated(model) && detail.quirky_family) output.push('<span class="badge warn" title="This model family has underperformed predictions in the past">Family caution</span>');
  return output.join("");
}

function rowHtml(model, rank) {
  const estimated = isEstimated(model);
  const parts = String(model.name || "").split(" - ");
  const harness = parts.length > 1 ? parts[0] : "";
  const modelName = parts.length > 1 ? parts.slice(1).join(" - ") : String(model.name || "");
  const harnessLabel = harness ? `<span class="harness">${esc(harness)}</span>` : "";
  const scoreNote = estimated ? `<small>predicted &plusmn;${num((model.detail?.band ?? 0.06) * 100, 0)}</small>` : `<small>coding score</small>`;
  return `<article class="row ${estimated ? "est-row" : ""}">
    <span class="rank">${rank}</span>
    <div class="model"><strong>${esc(modelName)}</strong>${harnessLabel}${badges(model)}</div>
    <div class="cell score-cell"><b>${num(quality(model))}</b>${scoreNote}</div>
    <div class="cell cell-task"><b>${money(model.cost_task)}</b><small>per task</small></div>
    <div class="cell cell-price"><b>${money(model.price_mtok)}</b><small>per 1M tokens</small></div>
    <div class="cell cell-time"><b>${minutes(model.wall_time_s)}</b><small>task time</small></div>
  </article>`;
}

function sortedByQuality() {
  return allModels().sort((a, b) => quality(b) - quality(a));
}

function sortedByBalance() {
  return allModels().sort((a, b) => blendedScore(b) - blendedScore(a));
}

function renderLeaderboard() {
  const rows = sortedByQuality();
  return `<section class="page">
    <div class="page-head">
      <h1>The best coding agents</h1>
      <p>Ranked by coding score out of 100. ${state.coding.length} measured on the benchmark, ${state.est.length} predicted before testing.</p>
    </div>
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost / task</span><span class="cell">$ / 1M tokens</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.map((model, index) => rowHtml(model, index + 1)).join("")}</div>
  </section>`;
}

function renderValue() {
  const rows = sortedByBalance();
  const weight = state.slider / 100;
  return `<section class="page">
    <div class="page-head">
      <h1>Cost vs quality</h1>
      <p>Move the slider to lean toward cheaper models or stronger ones. Cost here is the per-token price, so every model is compared on the same basis.</p>
    </div>
    <div class="slider-card">
      <div class="slider-ends"><span>Lean on <b>cost</b></span><span>Lean on <b>quality</b></span></div>
      <input type="range" id="balance" min="0" max="100" value="${state.slider}" aria-label="Balance between cost and quality">
      <div class="slider-readout">Right now: <b>${Math.round(weight * 100)}% quality</b> &middot; ${Math.round((1 - weight) * 100)}% cost &middot; leaning on ${leanLabel()}</div>
    </div>
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost / task</span><span class="cell">$ / 1M tokens</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.map((model, index) => rowHtml(model, index + 1)).join("")}</div>
  </section>`;
}

function renderRadar() {
  const radar = state.radar || {};
  const articles = radar.articles || [];
  const newModels = radar.new_models || [];
  const candidates = radar.candidates || [];
  const hn = (name) => `https://hn.algolia.com/?q=${encodeURIComponent(name)}`;
  const aa = (slug) => `https://artificialanalysis.ai/articles/${encodeURIComponent(slug || "")}`;
  const articlesHtml = articles.length ? articles.map((article) => `<a class="radar-row" href="${esc(aa(article.slug))}" target="_blank" rel="noopener"><span class="radar-date">${esc(article.date || "")}</span><span class="radar-title">${esc(article.title)}</span><span class="radar-arrow">&nearr;</span></a>`).join("") : `<div class="radar-empty">No articles recorded yet.</div>`;
  const newHtml = newModels.length ? newModels.map((entry) => `<div class="radar-row"><span class="radar-date">${esc(String(entry.ts || "").slice(0, 10))}</span><span class="radar-title">${esc(entry.name)} <em>new on ${esc(entry.source)}</em></span><a class="radar-arrow" href="${esc(hn(entry.name))}" target="_blank" rel="noopener" title="Search Hacker News">&nearr;</a></div>`).join("") : `<div class="radar-empty">No new benchmark entries since the first snapshot.</div>`;
  const candidatesHtml = candidates.length ? candidates.map((model) => `<div class="radar-row"><span class="radar-date">${num(model.coding_index, 1)}</span><span class="radar-title">${esc(model.name)} <em>predicted, not benchmarked</em></span><a class="radar-arrow" href="${esc(hn(model.name))}" target="_blank" rel="noopener" title="Search Hacker News">&nearr;</a></div>`).join("") : `<div class="radar-empty">Nothing to watch right now.</div>`;
  return `<section class="page">
    <div class="page-head">
      <h1>Release radar</h1>
      <p>The day-0 workflow, in one page: what just landed, what is new on the benchmarks, and which unbenchmarked models are worth a look.</p>
    </div>
    <h2 class="radar-heading">Just landed <span>Artificial Analysis changelog</span></h2>
    <div class="radar-list">${articlesHtml}</div>
    <h2 class="radar-heading">New on the benchmarks <span>from our own snapshots</span></h2>
    <div class="radar-list">${newHtml}</div>
    <h2 class="radar-heading">Worth watching <span>top predicted, not yet benchmarked</span></h2>
    <div class="radar-list">${candidatesHtml}</div>
    <p class="radar-note">Verdicts move for about a week after release. The arrow opens the Hacker News thread or the full AA article, where practitioners post hands-on reports.</p>
  </section>`;
}

function render() {
  const output = state.page === "value" ? renderValue() : state.page === "radar" ? renderRadar() : renderLeaderboard();
  $("#app").innerHTML = output;
  document.querySelectorAll(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.page === state.page));
  const slider = $("#balance");
  if (slider) {
    slider.addEventListener("input", () => {
      state.slider = Number(slider.value);
      $("#app").innerHTML = renderValue();
      bindNav();
    });
  }
}

function bindNav() {
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.page = button.dataset.page;
      render();
    });
  });
}

function updateHeader() {
  $("#last-update").textContent = state.staticMode ? "Static snapshot" : "Live data";
  $("#footer-updated").textContent = `${state.coding.length} measured + ${state.est.length} predicted coding models · auto-updated`;
}

async function loadData() {
  try {
    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) throw new Error("Static mode");
    const [coding, est, radar] = await Promise.all([
      fetch("/api/views/coding").then((response) => response.json()),
      fetch("/api/views/est").then((response) => response.json()),
      fetch("/api/radar").then((response) => response.json()),
    ]);
    state.coding = coding || [];
    state.est = est || [];
    state.radar = radar || {};
  } catch {
    state.staticMode = true;
    const data = await fetch("data.json", { cache: "no-store" }).then((response) => response.json());
    state.coding = data.coding || [];
    state.est = data.est || [];
    state.radar = data.radar || {};
  }
  updateHeader();
  render();
  bindNav();
}

loadData();
