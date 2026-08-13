const $ = (selector) => document.querySelector(selector);

const state = {
  coding: [],
  est: [],
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

function costOf(model) {
  return model.cost_task !== null && model.cost_task !== undefined ? model.cost_task : model.price_mtok;
}

function unitOf(model) {
  return model.cost_task !== null && model.cost_task !== undefined ? "task" : "price";
}

function costNorm(model) {
  const unit = unitOf(model);
  const costs = allModels().filter((other) => unitOf(other) === unit).map(costOf).filter((value) => value !== null && value !== undefined);
  if (costs.length < 2) return 0;
  const min = Math.min(...costs);
  const max = Math.max(...costs);
  const cost = costOf(model);
  if (cost === null || cost === undefined) return 0;
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
  const costNote = estimated ? `<small>per 1M tokens</small>` : `<small>per task</small>`;
  return `<article class="row ${estimated ? "est-row" : ""}">
    <span class="rank">${rank}</span>
    <div class="model"><strong>${esc(modelName)}</strong>${harnessLabel}${badges(model)}</div>
    <div class="cell score-cell"><b>${num(quality(model))}</b>${scoreNote}</div>
    <div class="cell"><b>${money(costOf(model))}</b>${costNote}</div>
    <div class="cell"><b>${minutes(model.wall_time_s)}</b><small>task time</small></div>
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
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.map((model, index) => rowHtml(model, index + 1)).join("")}</div>
  </section>`;
}

function renderValue() {
  const rows = sortedByBalance();
  const weight = state.slider / 100;
  return `<section class="page">
    <div class="page-head">
      <h1>Cost vs quality</h1>
      <p>Move the slider to lean toward cheaper models or stronger ones. Estimated models are included and marked, using their token price.</p>
    </div>
    <div class="slider-card">
      <div class="slider-ends"><span>Lean on <b>cost</b></span><span>Lean on <b>quality</b></span></div>
      <input type="range" id="balance" min="0" max="100" value="${state.slider}" aria-label="Balance between cost and quality">
      <div class="slider-readout">Right now: <b>${Math.round(weight * 100)}% quality</b> &middot; ${Math.round((1 - weight) * 100)}% cost &middot; leaning on ${leanLabel()}</div>
    </div>
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.map((model, index) => rowHtml(model, index + 1)).join("")}</div>
  </section>`;
}

function render() {
  $("#app").innerHTML = state.page === "value" ? renderValue() : renderLeaderboard();
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
    const [coding, est] = await Promise.all([
      fetch("/api/views/coding").then((response) => response.json()),
      fetch("/api/views/est").then((response) => response.json()),
    ]);
    state.coding = coding || [];
    state.est = est || [];
  } catch {
    state.staticMode = true;
    const data = await fetch("data.json", { cache: "no-store" }).then((response) => response.json());
    state.coding = data.coding || [];
    state.est = data.est || [];
  }
  updateHeader();
  render();
  bindNav();
}

loadData();
