const $ = (selector) => document.querySelector(selector);

const ROLE_ORDER = ["research", "general_coder", "ui_coder", "complex_code"];
const ROLE_LABELS = {
  research: "Research",
  general_coder: "General coder",
  ui_coder: "UI coder",
  complex_code: "Complex code",
};

const state = {
  models: [],
  recommendations: {},
  role: "general_coder",
  query: "",
  status: "all",
  sort: "role",
  sortDir: 1,
  view: "curated",
  staticMode: false,
  expanded: new Set(),
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

function tokenPriceLabel(model) {
  const detail = model.detail || {};
  const schedule = detail.price_schedule;
  if (schedule?.off_peak && schedule?.peak) {
    const offPeak = (schedule.off_peak[0] * 3 + schedule.off_peak[1]) / 4;
    const peak = (schedule.peak[0] * 3 + schedule.peak[1]) / 4;
    return `${money(offPeak)}-${money(peak)}`;
  }
  return money(model.price_mtok);
}

function tokenPriceNote(model) {
  return model.detail?.price_schedule ? "off-peak to peak / 1M tok" : "per 1M tokens";
}

function minutes(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "—";
  const mins = Math.round(Number(seconds) / 60);
  return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function measurementLabel(model) {
  switch (model.measurement_type) {
    case "aa_coding_agent": return "AA Coding Agent";
    case "aa_model_index": return "AA model index";
    case "predicted_coding_agent": return "Predicted";
    case "livebench": return "LiveBench";
    default: return "Limited evidence";
  }
}

function kindOf(model) {
  if (model.measurement_type === "aa_coding_agent") return "measured";
  if (model.measurement_type === "livebench") return "livebench";
  if (model.measurement_type === "predicted_coding_agent") return "estimated";
  return "model-index";
}

function roleData() {
  return state.recommendations[state.role] || { candidates: [], recommended: null };
}

function candidateMap() {
  return new Map((roleData().candidates || []).map((candidate) => [candidate.slug, candidate]));
}

function priceIn(model) {
  return model.detail?.price_input ?? null;
}

function priceOut(model) {
  return model.detail?.price_output ?? null;
}

function roleScoreValue(model) {
  const candidate = candidateMap().get(model.slug);
  return candidate?.role_score ?? model.coding_index ?? null;
}

function qualityValue(model) {
  const candidate = candidateMap().get(model.slug);
  return candidate?.quality_score ?? model.intelligence ?? null;
}

const MIN_VALUE_SCORE = 60;

function valueScore(model) {
  const out = priceOut(model);
  const score = roleScoreValue(model);
  if (out === null || out === undefined || Number(out) <= 0) return null;
  if (score === null || score === undefined || Number(score) < MIN_VALUE_SCORE) return null;
  return Number(score) / Number(out);
}

function isPriced(model) {
  return priceIn(model) !== null || priceOut(model) !== null;
}

function badges(model) {
  const output = [];
  const kind = kindOf(model);
  if (kind === "estimated") output.push('<span class="badge est" title="Regression estimate, not an agent benchmark">Predicted</span>');
  if (kind === "livebench") output.push('<span class="badge lb" title="LiveBench coding benchmark, separate from AA Coding Agent">LiveBench</span>');
  if (kind === "model-index") output.push('<span class="badge warn" title="Observed model leaderboard signal, not an agent run">Model index</span>');
  if (model.deprecated) output.push('<span class="badge warn">Deprecated</span>');
  if (model.is_new) output.push('<span class="badge new">New</span>');
  if (model.detail?.identity_status === "ambiguous_price_match") output.push('<span class="badge warn">Ambiguous price</span>');
  return output.join("");
}

function filteredModels() {
  let models = [...state.models];
  if (state.query) {
    const query = state.query.toLowerCase();
    models = models.filter((model) => String(model.name || "").toLowerCase().includes(query));
  }
  if (state.status !== "all") models = models.filter((model) => kindOf(model) === state.status);
  if (state.view === "curated") {
    const hasScore = (model) => model.coding_index !== null && model.coding_index !== undefined || model.intelligence !== null && model.intelligence !== undefined;
    models = models.filter((model) => isPriced(model) && hasScore(model));
  }
  const sortValue = (model, key) => {
    switch (key) {
      case "role":
        return roleScoreValue(model);
      case "general":
        return qualityValue(model);
      case "value":
        return valueScore(model);
      case "in":
        return priceIn(model);
      case "out":
        return priceOut(model);
      case "coding":
        return model.coding_index ?? null;
      case "visual":
        return model.vision ?? null;
      case "name":
        return String(model.name || "").toLowerCase();
      default:
        return roleScoreValue(model);
    }
  };
  const ascending = state.sort === "in" || state.sort === "out" || state.sort === "name";
  models.sort((a, b) => {
    if (state.sort === "name") return sortValue(a, "name").localeCompare(sortValue(b, "name")) * state.sortDir;
    const av = sortValue(a, state.sort);
    const bv = sortValue(b, state.sort);
    const aMissing = av === null || av === undefined || Number.isNaN(av);
    const bMissing = bv === null || bv === undefined || Number.isNaN(bv);
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;
    return (bv - av) * (ascending ? -1 : 1) * state.sortDir;
  });
  return models;
}

function statCards() {
  const pool = state.models.filter((model) => isPriced(model));
  const topScore = [...pool].sort((a, b) => (roleScoreValue(b) ?? -1) - (roleScoreValue(a) ?? -1))[0];
  const valuePool = pool.filter((model) => (roleScoreValue(model) ?? -1) >= MIN_VALUE_SCORE);
  const topValue = [...valuePool].sort((a, b) => (valueScore(b) ?? -1) - (valueScore(a) ?? -1))[0];
  const topScoreValue = roleScoreValue(topScore);
  const topValueScore = valueScore(topValue);
  const topValueOut = priceOut(topValue);
  const valueMeta = topValue && topValueScore !== null
    ? `${esc(topValue.name)} · ${money(topValueOut)}/1M out`
    : "No model clears the 60-score floor";
  return `<section class="stat-cards">
    <div class="stat-card"><span class="lbl">Models tracked</span><b class="big">${state.models.length}</b><small>${pool.length} with score and price</small></div>
    <div class="stat-card"><span class="lbl">Top ${ROLE_LABELS[state.role]} score</span><b class="big accent">${topScore ? num(topScoreValue) : "—"}</b><small>${topScore ? esc(topScore.name) : "No candidates"}</small></div>
    <div class="stat-card"><span class="lbl">Best value</span><b class="big gold">${topValueScore !== null ? num(topValueScore) : "—"}</b><small>${valueMeta} · 60+ score only</small></div>
  </section>`;
}

function roleCard(role) {
  const block = state.recommendations[role] || {};
  const model = block.recommended;
  const active = state.role === role ? "active" : "";
  const cost = model?.projected_cost_usd !== null && model?.projected_cost_usd !== undefined
    ? `${money(model.projected_cost_usd)}/turn`
    : "price unknown";
  const warning = model?.warnings?.[0] || block.description || "Insufficient evidence";
  return `<button class="pick-card ${active}" data-role="${role}">
    <span class="pick-label">${esc(ROLE_LABELS[role])}</span>
    <strong>${esc(model?.name || "No safe recommendation")}</strong>
    <span class="pick-meta">${model ? `${num(model.quality_score)} quality · ${cost}` : "Needs more evidence"}</span>
    <small>${esc(warning)}</small>
  </button>`;
}

function picksBar() {
  return `<section class="picks">${ROLE_ORDER.map(roleCard).join("")}</section>`;
}

function kindLabel(source, kind) {
  if (kind === "livebench_coding") return "LiveBench coding";
  if (kind === "livebench_agentic") return "LiveBench agentic";
  if (kind === "livebench_reasoning") return "LiveBench reasoning";
  if (kind === "aider_polyglot") return "Aider polyglot";
  if (kind === "evalplus") return "EvalPlus";
  if (kind === "tbench") return "Terminal-Bench";
  if (kind === "deepswe") return "DeepSWE";
  if (kind === "gorilla") return "BFCL tool use";
  if (kind && kind.startsWith("arena_")) return `Arena ${kind.replace("arena_", "")}`;
  if (kind && kind.startsWith("swebench_")) return `SWE-bench ${kind.replace("swebench_", "")}`;
  return source;
}

function rawValue(kind, raw) {
  if (raw === null || raw === undefined) return "—";
  return kind && kind.startsWith("arena_") ? String(Math.round(raw)) : num(raw, 1);
}

function detailHtml(model) {
  const detail = model.detail || {};
  const components = model.components || {};
  const candidate = candidateMap().get(model.slug);
  const benchmarkRows = [];
  for (const [lane, block] of Object.entries(components)) {
    if (!block || typeof block !== "object") continue;
    if (lane === "coding_agent" || lane === "intelligence") {
      benchmarkRows.push({ label: lane === "coding_agent" ? "AA Coding Agent" : "General intelligence", value: block.value, note: block.estimated ? "estimated source" : "observed source" });
      continue;
    }
    for (const source of block.sources || []) {
      benchmarkRows.push({ label: kindLabel(source.source, source.kind), value: rawValue(source.kind, source.raw), note: source.name });
    }
  }
  const benchmarkHtml = benchmarkRows.length
    ? benchmarkRows.slice(0, 16).map((row) => `<div class="bench-row"><span>${esc(row.label)}</span><b>${esc(String(row.value))}</b><small>${esc(row.note || "")}</small></div>`).join("")
    : `<div class="drawer-note">No benchmark evidence recorded for this model.</div>`;
  const warnings = [];
  if (model.measurement_type === "predicted_coding_agent") warnings.push(`Predicted coding score with +/-${num(detail.band_points ?? model.band, 1)} points uncertainty.`);
  if (model.measurement_type === "aa_model_index") warnings.push("This is an observed AA model-index signal, not a Coding Agent run.");
  if (detail.agrees === false) warnings.push("The regression cross-checks disagree.");
  if (detail.extrapolated) warnings.push("This estimate is outside the fitted intelligence range.");
  if (detail.identity_status === "ambiguous_price_match") warnings.push("Provider price matching was ambiguous and was not used for the recommendation.");
  if (model.deprecated) warnings.push("The source marks this model as deprecated.");
  if (candidate?.warnings?.length) warnings.push(...candidate.warnings);
  const warningsHtml = warnings.length ? `<div class="detail-warnings">${[...new Set(warnings)].map((warning) => `<div class="drawer-warning">${esc(warning)}</div>`).join("")}</div>` : "";
  return `<div class="detail">
    <div class="detail-grid">
      <div class="detail-block"><h4>Evidence</h4><div class="bench-grid">${benchmarkHtml}</div></div>
      <div class="detail-block"><h4>Capability and cost</h4>
        <div class="spec-grid">
          <div class="spec-row"><span>Measurement</span><b>${esc(measurementLabel(model))}</b></div>
          <div class="spec-row"><span>Evidence coverage</span><b>${model.coverage !== null && model.coverage !== undefined ? `${num(model.coverage * 100, 0)}%` : "—"}</b></div>
          <div class="spec-row"><span>Tool support</span><b>${esc(candidate?.supports_tools || (model.supports_tools === true ? "verified" : "unknown"))}</b></div>
          <div class="spec-row"><span>Image input</span><b>${model.accepts_image === null || model.accepts_image === undefined ? "unknown" : model.accepts_image ? "yes" : "no"}</b></div>
          <div class="spec-row"><span>Context window</span><b>${model.context_window ? `${Math.round(model.context_window / 1000)}k tokens` : "—"}</b></div>
          <div class="spec-row"><span>Output speed</span><b>${model.output_speed ? `${num(model.output_speed, 0)} tok/s` : "—"}</b></div>
          <div class="spec-row"><span>Projected OpenCode turn</span><b>${candidate?.projected_cost_usd !== null && candidate?.projected_cost_usd !== undefined ? money(candidate.projected_cost_usd) : "—"}</b></div>
          <div class="spec-row"><span>Benchmark task cost</span><b>${money(model.cost_task)}</b></div>
          <div class="spec-row"><span>Token price</span><b>${tokenPriceLabel(model)}</b></div>
          <div class="spec-row"><span>Price basis</span><b>${esc(model.cost_basis || "unknown")}</b></div>
        </div>
        ${warningsHtml}
      </div>
    </div>
  </div>`;
}

function rowHtml(model, rank) {
  const kind = kindOf(model);
  const candidate = candidateMap().get(model.slug);
  const parts = String(model.name || "").split(" - ");
  const harness = parts.length > 1 ? parts[0] : "";
  const modelName = parts.length > 1 ? parts.slice(1).join(" - ") : String(model.name || "");
  const expanded = state.expanded.has(model.slug);
  const mainValue = candidate?.role_score ?? model.coding_index;
  const mainNote = candidate ? `${ROLE_LABELS[state.role]} score` : measurementLabel(model);
  const secondaryValue = candidate?.quality_score ?? model.intelligence;
  const secondaryNote = candidate ? "quality" : "general";
  const value = valueScore(model);
  const inPrice = priceIn(model);
  const outPrice = priceOut(model);
  return `<div class="mgroup">
    <article class="row ${kind === "estimated" ? "est-row" : ""} ${kind === "livebench" ? "lb-row" : ""} ${expanded ? "open" : ""}" data-slug="${esc(model.slug)}" tabindex="0" role="button" aria-expanded="${expanded}">
      <span class="rank">${rank}</span>
      <div class="model"><strong>${esc(modelName)}</strong>${harness ? `<span class="harness">${esc(harness)}</span>` : ""}${badges(model)}</div>
      <div class="cell score-cell"><b>${num(mainValue)}</b><small>${esc(mainNote)}</small></div>
      <div class="cell cell-quality"><b>${num(secondaryValue)}</b><small>${secondaryNote}</small></div>
      <div class="cell value-cell"><b>${value !== null && value !== undefined ? num(value) : "—"}</b><small>pts / $1M out</small></div>
      <div class="cell mono-cell cell-in"><b>${inPrice !== null && inPrice !== undefined ? money(inPrice) : "—"}</b><small>in / 1M tok</small></div>
      <div class="cell mono-cell cell-out"><b>${outPrice !== null && outPrice !== undefined ? money(outPrice) : "—"}</b><small>out / 1M tok</small></div>
      <div class="expand">${expanded ? "−" : "+"}</div>
    </article>
    ${expanded ? detailHtml(model) : ""}
  </div>`;
}

function headCell(key, label) {
  const cls = { general: "cell-quality", value: "cell-value", in: "cell-in", out: "cell-out" }[key] || "";
  const active = state.sort === key;
  const arrow = active ? (state.sortDir === 1 ? " ▼" : " ▲") : "";
  return `<button class="head-cell ${cls} ${active ? "active" : ""}" data-sort-key="${key}" title="Click to sort">${label}${arrow}</button>`;
}

function controls() {
  const roleButtons = ROLE_ORDER.map((role) => `<button class="filter-button mode-button ${state.role === role ? "active" : ""}" data-role="${role}">${ROLE_LABELS[role]}</button>`).join("");
  const statusButton = (status, label) => `<button class="filter-button ${state.status === status ? "active" : ""}" data-status="${status}">${label}</button>`;
  const viewButton = (view, label) => `<button class="filter-button ${state.view === view ? "active" : ""}" data-view="${view}">${label}</button>`;
  return `<section class="controls">
    <label class="search-wrap"><span>⌕</span><input id="model-search" type="search" placeholder="Search any model" value="${esc(state.query)}" aria-label="Search models"></label>
    <div class="filter-group" role="group" aria-label="Recommendation role">${roleButtons}</div>
    <div class="filter-group" role="group" aria-label="Catalog view">${viewButton("curated", "Priced")}${viewButton("all", `All ${state.models.length}`)}</div>
    <div class="filter-group" role="group" aria-label="Evidence type">${statusButton("all", "All")}${statusButton("measured", "Measured")}${statusButton("model-index", "Model index")}${statusButton("estimated", "Predicted")}${statusButton("livebench", "LiveBench")}</div>
    <select class="sort-select" id="sort-select" aria-label="Sort models">
      <option value="role" ${state.sort === "role" ? "selected" : ""}>Sort: role score</option>
      <option value="coding" ${state.sort === "coding" ? "selected" : ""}>Sort: coding signal</option>
      <option value="general" ${state.sort === "general" ? "selected" : ""}>Sort: quality</option>
      <option value="visual" ${state.sort === "visual" ? "selected" : ""}>Sort: visual score</option>
      <option value="value" ${state.sort === "value" ? "selected" : ""}>Sort: value</option>
      <option value="in" ${state.sort === "in" ? "selected" : ""}>Sort: input price</option>
      <option value="out" ${state.sort === "out" ? "selected" : ""}>Sort: output price</option>
      <option value="name" ${state.sort === "name" ? "selected" : ""}>Sort: name A-Z</option>
    </select>
  </section>`;
}

function render() {
  const rows = filteredModels();
  const recommendation = roleData();
  const budget = recommendation.budget_usd !== null && recommendation.budget_usd !== undefined ? ` Default budget: ${money(recommendation.budget_usd)}/turn.` : " Price is not part of this role's objective.";
  const listHead = `<div class="list-head"><span class="rank">#</span>${headCell("name", "Model")}${headCell("role", "Role score")}${headCell("general", "Quality")}${headCell("value", "Value")}${headCell("in", "In $/1M")}${headCell("out", "Out $/1M")}<span class="expand-head"></span></div>`;
  const description = recommendation.description || "Recommendations are based on benchmark evidence, capability, freshness, and workload cost.";
  $("#app").innerHTML = `<section class="page">
    <div class="page-head">
      <h1>Pick a model<br>for the actual job.</h1>
      <p>${esc(description)}${esc(budget)} Recommendations distinguish measured agent runs, model-index signals, benchmark support, and regression predictions.</p>
    </div>
    ${statCards()}
    ${picksBar()}
    ${controls()}
    ${listHead}
    <div class="list">${rows.length ? rows.map((model, index) => rowHtml(model, index + 1)).join("") : `<div class="empty-state">No models match. Try another role or evidence filter.</div>`}</div>
    <p class="radar-note">${rows.length} of ${state.models.length} models shown${state.view === "curated" ? " (priced only — switch to All to see the full catalog)" : ""}. Value = role score per $1M of output tokens. Recommendations are calculated server-side from benchmark lanes and the configured OpenCode workload.</p>
  </section>`;
  wireEvents();
}

function wireEvents() {
  const search = $("#model-search");
  if (search) search.addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
    $("#model-search")?.focus();
  });
  document.querySelectorAll("[data-role]").forEach((button) => button.addEventListener("click", () => { state.role = button.dataset.role; state.sort = "role"; state.sortDir = 1; render(); }));
  document.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", () => { state.status = button.dataset.status; render(); }));
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => { state.view = button.dataset.view; render(); }));
  const sort = $("#sort-select");
  if (sort) sort.addEventListener("change", (event) => { state.sort = event.target.value; state.sortDir = 1; render(); });
  document.querySelectorAll("[data-sort-key]").forEach((head) => head.addEventListener("click", () => {
    const key = head.dataset.sortKey;
    if (state.sort === key) state.sortDir *= -1;
    else { state.sort = key; state.sortDir = 1; }
    render();
  }));
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
  const recommendation = roleData();
  $("#last-update").textContent = state.staticMode ? "Static snapshot" : "Live data";
  $("#footer-updated").textContent = `${state.models.length} models · ${recommendation.recommended ? `recommended: ${recommendation.recommended.name}` : "no recommendation"}`;
}

async function loadData() {
  try {
    const statusResponse = await fetch("/api/status");
    if (!statusResponse.ok) throw new Error("Static mode");
    const [models, recommendations] = await Promise.all([
      fetch("/api/views/models").then((response) => response.json()),
      fetch("/api/recommendations").then((response) => response.json()),
    ]);
    state.models = models || [];
    state.recommendations = recommendations || {};
  } catch {
    state.staticMode = true;
    const data = await fetch("data.json", { cache: "no-store" }).then((response) => response.json());
    state.models = data.models || [...(data.coding || []), ...(data.est || []), ...(data.livebench || [])];
    state.recommendations = data.recommendations || {};
  }
  updateHeader();
  render();
}

loadData();
