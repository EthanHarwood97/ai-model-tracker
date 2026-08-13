const $ = (selector) => document.querySelector(selector);

const state = {
  coding: [],
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

function quality(coding) {
  return Number(coding.coding_index || 0);
}

function costOf(coding) {
  return coding.cost_task !== null && coding.cost_task !== undefined ? coding.cost_task : coding.price_mtok;
}

function costNorm(coding) {
  const costs = state.coding.map(costOf).filter((value) => value !== null && value !== undefined);
  if (costs.length < 2) return 0;
  const min = Math.min(...costs);
  const max = Math.max(...costs);
  const cost = costOf(coding);
  if (cost === null || cost === undefined) return 0;
  return max === min ? 0 : (cost - min) / (max - min);
}

function blendedScore(coding) {
  const weight = state.slider / 100;
  const costScore = (1 - costNorm(coding)) * 100;
  return weight * quality(coding) + (1 - weight) * costScore;
}

function leanLabel() {
  if (state.slider >= 60) return "quality";
  if (state.slider <= 40) return "cost";
  return "a balance of both";
}

function badges(coding) {
  const output = [];
  if (coding.is_new) output.push('<span class="badge new">New</span>');
  return output.join("");
}

function rowHtml(coding, rank) {
  const parts = String(coding.name || "").split(" - ");
  const harness = parts.length > 1 ? parts[0] : "";
  const modelName = parts.length > 1 ? parts.slice(1).join(" - ") : String(coding.name || "");
  const harnessLabel = harness ? `<span class="harness">${esc(harness)}</span>` : "";
  return `<article class="row">
    <span class="rank">${rank}</span>
    <div class="model"><strong>${esc(modelName)}</strong>${harnessLabel}${badges(coding)}</div>
    <div class="cell score-cell"><b>${num(quality(coding))}</b><small>coding score</small></div>
    <div class="cell"><b>${money(costOf(coding))}</b><small>per task</small></div>
    <div class="cell"><b>${minutes(coding.wall_time_s)}</b><small>task time</small></div>
  </article>`;
}

function sortedByQuality() {
  return [...state.coding].sort((a, b) => quality(b) - quality(a));
}

function sortedByBalance() {
  return [...state.coding].sort((a, b) => blendedScore(b) - blendedScore(a));
}

function renderLeaderboard() {
  const rows = sortedByQuality();
  return `<section class="page">
    <div class="page-head">
      <h1>The best coding agents</h1>
      <p>Ranked by the Artificial Analysis coding agent score, out of 100. Includes cost and time per task.</p>
    </div>
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost / task</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.map((coding, index) => rowHtml(coding, index + 1)).join("")}</div>
  </section>`;
}

function renderValue() {
  const rows = sortedByBalance();
  const weight = state.slider / 100;
  return `<section class="page">
    <div class="page-head">
      <h1>Cost vs quality</h1>
      <p>Move the slider to lean toward cheaper models or stronger ones. The ranking updates instantly.</p>
    </div>
    <div class="slider-card">
      <div class="slider-ends"><span>Lean on <b>cost</b></span><span>Lean on <b>quality</b></span></div>
      <input type="range" id="balance" min="0" max="100" value="${state.slider}" aria-label="Balance between cost and quality">
      <div class="slider-readout">Right now: <b>${Math.round(weight * 100)}% quality</b> · ${Math.round((1 - weight) * 100)}% cost · leaning on ${leanLabel()}</div>
    </div>
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Score</span><span class="cell">Cost / task</span><span class="cell">Time / task</span></div>
    <div class="list">${rows.map((coding, index) => rowHtml(coding, index + 1)).join("")}</div>
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
  const timestamp = state.staticMode ? "Static snapshot" : "Live data";
  $("#last-update").textContent = timestamp;
  $("#footer-updated").textContent = `${state.coding.length} coding agents · auto-updated`;
}

async function loadData() {
  try {
    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) throw new Error("Static mode");
    const coding = await fetch("/api/views/coding").then((response) => response.json());
    state.coding = coding || [];
  } catch {
    state.staticMode = true;
    const data = await fetch("data.json", { cache: "no-store" }).then((response) => response.json());
    state.coding = data.coding || [];
  }
  updateHeader();
  render();
  bindNav();
}

loadData();
