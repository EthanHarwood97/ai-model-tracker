const $ = (selector) => document.querySelector(selector);

const state = {
  coding: [],
  est: [],
  page: "budget",
  staticMode: false,
};

const tiers = {
  budget: {
    label: "Budget picks",
    title: "Good models. Very low cost.",
    description: "The models to reach for first when you want strong coding help without spending much.",
    rule: "Up to $0.50 per task",
  },
  workhorse: {
    label: "Workhorse picks",
    title: "A little more room to work.",
    description: "The practical middle ground: more capable than the budget tier, without paying frontier prices.",
    rule: "$0.50 to $3.00 per task",
  },
  frontier: {
    label: "Frontier picks",
    title: "For the hardest jobs.",
    description: "The strongest coding agents in the current snapshot. Price is secondary here.",
    rule: "Top coding scores, any price",
  },
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
  return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function quality(model) {
  return Number(model.coding_index || 0);
}

function spend(model) {
  return model.cost_task !== null && model.cost_task !== undefined ? model.cost_task : model.price_mtok;
}

function isEstimated(model) {
  return !model.measured;
}

function allModels() {
  return [...state.coding, ...state.est];
}

function badges(model) {
  const output = [];
  const detail = model.detail || {};
  if (isEstimated(model)) output.push('<span class="badge est" title="Predicted score: not yet measured on the coding-agent benchmark">Estimated</span>');
  if (model.is_new) output.push('<span class="badge new">New</span>');
  if (isEstimated(model) && detail.quirky_family) output.push('<span class="badge warn">Family caution</span>');
  return output.join("");
}

function tierRows(kind) {
  const models = allModels().filter((model) => spend(model) !== null && spend(model) !== undefined);
  if (kind === "frontier") return models.sort((a, b) => quality(b) - quality(a)).slice(0, 25);
  if (kind === "budget") return models.filter((model) => spend(model) <= 0.5 && quality(model) >= 50).sort((a, b) => quality(b) - quality(a));
  return models.filter((model) => spend(model) > 0.5 && spend(model) <= 3 && quality(model) >= 50).sort((a, b) => quality(b) - quality(a));
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

function renderTier(kind) {
  const tier = tiers[kind];
  const rows = tierRows(kind);
  const estimatedCount = rows.filter(isEstimated).length;
  return `<section class="page">
    <div class="page-head">
      <span class="eyebrow">${esc(tier.label)}</span>
      <h1>${tier.title}</h1>
      <p>${tier.description} ${estimatedCount ? `${estimatedCount} predicted model${estimatedCount === 1 ? "" : "s"} included and marked.` : ""}</p>
    </div>
    <div class="tier-summary"><b>${esc(tier.rule)}</b><span>Measured models use cost per task. Estimated models use their listed price per 1M tokens.</span></div>
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost / task</span><span class="cell">$ / 1M tokens</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.length ? rows.map((model, index) => rowHtml(model, index + 1)).join("") : `<div class="empty-state">No models match this tier yet.</div>`}</div>
  </section>`;
}

function render() {
  $("#app").innerHTML = renderTier(state.page);
  document.querySelectorAll(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.page === state.page));
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
  $("#footer-updated").textContent = `${state.coding.length} measured + ${state.est.length} predicted models · auto-updated`;
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
