const $ = (selector) => document.querySelector(selector);

const state = {
  coding: [],
  est: [],
  livebench: [],
  query: "",
  tier: "all",
  sort: "coding",
  status: "all",
  staticMode: false,
  expanded: new Set(),
};

const TIER_NAMES = {
  all: "All models",
  budget: "Budget",
  workhorse: "Workhorse",
  frontier: "Frontier",
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

function kindOf(model) {
  if (model.measured) return "measured";
  if (model.detail?.source === "livebench") return "livebench";
  return "estimated";
}

function allModels() {
  return [...state.coding, ...state.est, ...state.livebench];
}

function badges(model) {
  const detail = model.detail || {};
  const output = [];
  if (kindOf(model) === "livebench") output.push('<span class="badge lb" title="LiveBench coding score: a different benchmark from the AA coding-agent test">LiveBench</span>');
  if (kindOf(model) === "estimated") output.push('<span class="badge est" title="Predicted score: not yet measured on the coding-agent benchmark">Estimated</span>');
  if (model.is_new) output.push('<span class="badge new">New</span>');
  if (detail.quirky_family) output.push('<span class="badge warn">Family caution</span>');
  return output.join("");
}

function filteredModels() {
  let models = allModels();
  if (state.query) {
    const query = state.query.toLowerCase();
    models = models.filter((model) => String(model.name || "").toLowerCase().includes(query));
  }
  if (state.tier !== "all") {
    models = models.filter((model) => {
      const cost = spend(model);
      if (cost === null || cost === undefined) return false;
      if (state.tier === "budget") return cost <= 0.5;
      if (state.tier === "workhorse") return cost > 0.5 && cost <= 3;
      return cost > 3;
    });
  }
  if (state.status !== "all") models = models.filter((model) => kindOf(model) === state.status);
  models.sort((a, b) => {
    if (state.sort === "general") return Number(b.intelligence || 0) - Number(a.intelligence || 0);
    if (state.sort === "price") return (spend(a) ?? Infinity) - (spend(b) ?? Infinity);
    if (state.sort === "value") {
      const valueA = (spend(a) ?? Infinity) ? quality(a) / (spend(a) ?? Infinity) : 0;
      const valueB = (spend(b) ?? Infinity) ? quality(b) / (spend(b) ?? Infinity) : 0;
      return valueB - valueA;
    }
    return quality(b) - quality(a);
  });
  return models;
}

function tierFilter(kind) {
  return (model) => {
    const cost = spend(model);
    if (cost === null || cost === undefined) return false;
    if (kind === "budget") return cost <= 0.5;
    if (kind === "workhorse") return cost > 0.5 && cost <= 3;
    return cost > 3;
  };
}

function pickFor(kind) {
  const models = allModels().filter(tierFilter(kind));
  const best = [...models].sort((a, b) => quality(b) - quality(a))[0];
  return best;
}

function picksBar() {
  const budget = pickFor("budget");
  const workhorse = pickFor("workhorse");
  const overall = [...allModels()].sort((a, b) => quality(b) - quality(a))[0];
  const card = (label, model, tier, note) => `<button class="pick-card ${state.tier === tier ? "active" : ""}" data-tier="${tier}">
    <span class="pick-label">${label}</span>
    <strong>${esc(model ? model.name : "—")}</strong>
    <span class="pick-meta">${model ? `${num(quality(model))} score · ${money(spend(model))}${spend(model) === model?.cost_task ? "/task" : model?.price_mtok ? "/1M tok" : ""}` : ""}</span>
    <small>${note}</small>
  </button>`;
  return `<section class="picks">${card("Cheap and good", budget, "budget", "under $0.50 a task")}${card("The workhorse", workhorse, "workhorse", "$0.50 to $3 a task")}${card("The best there is", overall, "frontier", "top score, any price")}</section>`;
}

function kindLabel(source, kind) {
  if (kind === "livebench_global") return "LiveBench overall";
  if (kind === "livebench_coding") return "LiveBench coding";
  if (kind === "livebench_reasoning") return "LiveBench reasoning";
  if (kind === "livebench_agentic") return "LiveBench agentic";
  if (kind === "aider_polyglot") return "Aider polyglot";
  if (kind === "evalplus") return "EvalPlus";
  if (kind === "hf_openllm") return "HF open leaderboard";
  if (kind === "tbench") return "Terminal-Bench";
  if (kind === "deepswe") return "DeepSWE";
  if (kind === "gorilla") return "BFCL tool use";
  if (kind && kind.startsWith("arena_")) {
    const arena = kind.replace("arena_", "").replace("_overall", "");
    return `Arena ${arena} (Elo)`;
  }
  if (kind && kind.startsWith("swebench_")) return `SWE-bench ${kind.replace("swebench_", "")}`;
  return source;
}

function rawValue(source, kind, raw) {
  if (raw === null || raw === undefined) return "—";
  const isElo = kind && kind.startsWith("arena_");
  if (isElo) return String(Math.round(raw));
  return num(raw, 1);
}

function detailHtml(model) {
  const detail = model.detail || {};
  const components = model.components || {};
  const benchmarkRows = [];
  if (components.coding_agent) {
    benchmarkRows.push({ label: "Coding agent", value: components.coding_agent.value, note: components.coding_agent.estimated ? "predicted" : "measured on the AA agent test" });
  } else if (quality(model) > 0) {
    benchmarkRows.push({ label: "Coding", value: quality(model), note: kindOf(model) === "livebench" ? "LiveBench coding" : "predicted" });
  }
  if (model.intelligence !== null && model.intelligence !== undefined) benchmarkRows.push({ label: "General intelligence", value: model.intelligence, note: "AA Intelligence Index" });
  for (const [category, block] of Object.entries(components)) {
    if (category === "coding_agent" || category === "intelligence") continue;
    for (const source of block.sources || []) {
      benchmarkRows.push({ label: kindLabel(source.source, source.kind), value: rawValue(source.source, source.kind, source.raw), note: source.name });
    }
  }
  const benchmarkHtml = benchmarkRows.length
    ? benchmarkRows.slice(0, 12).map((row) => `<div class="bench-row"><span>${esc(row.label)}</span><b>${esc(String(row.value))}</b><small>${esc(row.note || "")}</small></div>`).join("")
    : `<div class="drawer-note">No benchmark data recorded for this model.</div>`;
  const warnings = [];
  if (kindOf(model) === "estimated") warnings.push(`Predicted score with a +/-${num((detail.band ?? 0.06) * 100, 0)} error band.`);
  if (detail.quirky_family) warnings.push("This model family has been less reliable at coding than its general score suggests.");
  if (detail.agrees === false) warnings.push("The two prediction checks disagree, so treat this result carefully.");
  if (detail.extrapolated) warnings.push("This estimate sits outside the range the prediction method was built on.");
  const warningsHtml = warnings.length ? `<div class="detail-warnings">${warnings.map((warning) => `<div class="drawer-warning">${esc(warning)}</div>`).join("")}</div>` : "";
  const adjusted = detail.cost_adjusted ? `<small>scaled to current API pricing</small>` : "";
  return `<div class="detail">
    <div class="detail-grid">
      <div class="detail-block"><h4>Benchmarks</h4><div class="bench-grid">${benchmarkHtml}</div></div>
      <div class="detail-block"><h4>Specs and price</h4>
        <div class="spec-grid">
          <div class="spec-row"><span>Context window</span><b>${model.context_window ? `${Math.round(model.context_window / 1000)}k tokens` : "—"}</b></div>
          <div class="spec-row"><span>Output speed</span><b>${model.output_speed ? `${num(model.output_speed, 0)} tok/s` : "—"}</b></div>
          <div class="spec-row"><span>Time per task</span><b>${minutes(model.wall_time_s)}</b></div>
          <div class="spec-row"><span>Cost per task</span><b>${money(model.cost_task)}</b>${adjusted}</div>
          <div class="spec-row"><span>Price per 1M tokens</span><b>${money(model.price_mtok)}</b></div>
          <div class="spec-row"><span>Input / output</span><b>${money(detail.price_input)} / ${money(detail.price_output)}</b></div>
        </div>
        ${warningsHtml}
      </div>
    </div>
  </div>`;
}

function rowHtml(model, rank) {
  const kind = kindOf(model);
  const parts = String(model.name || "").split(" - ");
  const harness = parts.length > 1 ? parts[0] : "";
  const modelName = parts.length > 1 ? parts.slice(1).join(" - ") : String(model.name || "");
  const harnessLabel = harness ? `<span class="harness">${esc(harness)}</span>` : "";
  const expanded = state.expanded.has(model.slug);
  const scoreNote = kind === "estimated" ? `predicted +/-${num((model.detail?.band ?? 0.06) * 100, 0)}` : kind === "livebench" ? "LiveBench coding" : "coding score";
  return `<div class="mgroup">
    <article class="row ${kind === "estimated" ? "est-row" : ""} ${kind === "livebench" ? "lb-row" : ""} ${expanded ? "open" : ""}" data-slug="${esc(model.slug)}" tabindex="0" role="button" aria-expanded="${expanded}">
      <span class="rank">${rank}</span>
      <div class="model"><strong>${esc(modelName)}</strong>${harnessLabel}${badges(model)}</div>
      <div class="cell score-cell"><b>${num(quality(model))}</b><small>${scoreNote}</small></div>
      <div class="cell"><b>${num(model.intelligence)}</b><small>general</small></div>
      <div class="cell cell-task"><b>${money(model.cost_task)}</b><small>per task</small></div>
      <div class="cell cell-price"><b>${money(model.price_mtok)}</b><small>per 1M tokens</small></div>
      <div class="expand">${expanded ? "−" : "+"}</div>
    </article>
    ${expanded ? detailHtml(model) : ""}
  </div>`;
}

function controls() {
  const tierButton = (tier) => `<button class="filter-button ${state.tier === tier ? "active" : ""}" data-tier="${tier}">${TIER_NAMES[tier]}</button>`;
  const statusButton = (status, label) => `<button class="filter-button ${state.status === status ? "active" : ""}" data-status="${status}">${label}</button>`;
  return `<section class="controls">
    <label class="search-wrap"><span>&#128269;</span><input id="model-search" type="search" placeholder="Search any model" value="${esc(state.query)}" aria-label="Search models"></label>
    <div class="filter-group" role="group" aria-label="Price tier">${tierButton("all")}${tierButton("budget")}${tierButton("workhorse")}${tierButton("frontier")}</div>
    <div class="filter-group" role="group" aria-label="Score type">${statusButton("all", "All")}${statusButton("measured", "Measured")}${statusButton("estimated", "Estimated")}${statusButton("livebench", "LiveBench")}</div>
    <select class="sort-select" id="sort-select" aria-label="Sort models">
      <option value="coding" ${state.sort === "coding" ? "selected" : ""}>Sort: coding score</option>
      <option value="general" ${state.sort === "general" ? "selected" : ""}>Sort: general score</option>
      <option value="value" ${state.sort === "value" ? "selected" : ""}>Sort: best value</option>
      <option value="price" ${state.sort === "price" ? "selected" : ""}>Sort: cheapest first</option>
    </select>
  </section>`;
}

function render() {
  const rows = filteredModels();
  $("#app").innerHTML = `<section class="page">
    <div class="page-head">
      <h1>Pick the right model<br>for the job.</h1>
      <p>Every coding model we track, in one list. Filter by price, search any name, tap a row to see every benchmark, price, and caveat we have on it.</p>
    </div>
    ${picksBar()}
    ${controls()}
    <div class="list-head"><span class="rank">#</span><span class="model">Model</span><span class="cell">Coding</span><span class="cell">General</span><span class="cell">Cost / task</span><span class="cell">$ / 1M tokens</span><span class="expand-head"></span></div>
    <div class="list">${rows.length ? rows.map((model, index) => rowHtml(model, index + 1)).join("") : `<div class="empty-state">No models match. Try a different search or filter.</div>`}</div>
    <p class="radar-note">${rows.length} model${rows.length === 1 ? "" : "s"} shown. Estimated scores are predictions until a model appears on the coding-agent benchmark. LiveBench rows use that benchmark's coding score.</p>
  </section>`;
  wireEvents();
}

function wireEvents() {
  const search = $("#model-search");
  if (search) {
    search.addEventListener("input", (event) => { state.query = event.target.value; render(); search.focus(); search.setSelectionRange(search.value.length, search.value.length); });
  }
  document.querySelectorAll("[data-tier]").forEach((button) => button.addEventListener("click", () => { state.tier = button.dataset.tier; render(); }));
  document.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", () => { state.status = button.dataset.status; render(); }));
  const sort = $("#sort-select");
  if (sort) sort.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
  document.querySelectorAll("[data-slug]").forEach((row) => {
    row.addEventListener("click", () => {
      const slug = row.dataset.slug;
      if (state.expanded.has(slug)) state.expanded.delete(slug);
      else state.expanded.add(slug);
      render();
    });
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        row.click();
      }
    });
  });
}

function updateHeader() {
  $("#last-update").textContent = state.staticMode ? "Static snapshot" : "Live data";
  $("#footer-updated").textContent = `${state.coding.length} measured · ${state.est.length} predicted · ${state.livebench.length} LiveBench-only · auto-updated`;
}

async function loadData() {
  try {
    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) throw new Error("Static mode");
    const [coding, est, livebench] = await Promise.all([
      fetch("/api/views/coding").then((response) => response.json()),
      fetch("/api/views/est").then((response) => response.json()),
      fetch("/api/views/livebench").then((response) => response.json()),
    ]);
    state.coding = coding || [];
    state.est = est || [];
    state.livebench = livebench || [];
  } catch {
    state.staticMode = true;
    const data = await fetch("data.json", { cache: "no-store" }).then((response) => response.json());
    state.coding = data.coding || [];
    state.est = data.est || [];
    state.livebench = data.livebench || [];
  }
  updateHeader();
  render();
}

loadData();
