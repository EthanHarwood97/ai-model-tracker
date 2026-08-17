# AI Model Score Tracker

Self-hosted, multi-source tracker for AI model evidence. Polls public
leaderboards, keeps benchmark types separate, and produces four
role-specific recommendations:

- Research / lightweight agent
- General coder
- UI coder
- Complex code

Predicted scores, model-index scores, and Coding Agent measurements are kept
separate. The aggregate meta score remains available as a coverage summary,
but it is not used as a substitute for a role recommendation.

Runs on Windows with only `httpx` + `fastapi` + `uvicorn`. Data lives in a
single SQLite file with per-source snapshots and a change log.

## Running online (GitHub Actions + Pages, $0)

This repo is set up to run itself in the cloud — no local machine needed:

- `.github/workflows/track.yml` runs `python -m model_tracker.cli publish` every
  30 minutes on GitHub's free runners (public repos get unlimited minutes).
- Each run fetches all sources fresh, rebuilds history from `snapshots/*.json`,
  diffs against the previous snapshot (NEW/updated/removed events), computes
  scores, and commits:
  - `snapshots/<source>/<ts>.json` — full per-source history, written only
    when data actually changed (git-friendly, diffable)
  - `docs/` — static dashboard (same UI as local, loads `data.json`)
- GitHub Pages serves `docs/` from the `main` branch at
  `https://<you>.github.io/ai-model-tracker/`.
- Push notifications on NEW models: set `alerts.webhook_url` in `config.json`
  to an ntfy.sh topic URL (e.g. `https://ntfy.sh/your-random-topic`), then
  install the ntfy app. Pick an unguessable topic name — the repo is public.

Manual trigger: `gh workflow run track.yml` (or the Actions tab → Run workflow).

Local usage still works exactly as before; `publish` uses a separate
`data/publish.db` so local and cloud histories never collide.

## Quick start

```powershell
python -m model_tracker.cli run-once     # scrape everything once + print summary
python -m model_tracker.cli serve        # scheduler + dashboard on http://127.0.0.1:8137
python -m model_tracker.cli summary      # print latest scores from the db
python -m model_tracker.cli scrape lmarena --verbose   # debug one source
# or: .\run.ps1
```

On first run the AA scrapers are self-verified against known-good values
(see `scripts/verify_aa.py`). The first `run-once` takes ~4 min (HF datasets
server index warm-up); everything is disk-cached afterwards.

## Dashboard views

- **Role recommendations** – four recommendations with evidence, confidence,
  projected OpenCode-turn cost, and warnings.
- **Evidence explorer** – one model list with measured Coding Agent results,
  model-index signals, benchmark support, and predictions labelled separately.
- **Coding evidence** – AA Coding Agent measurements, benchmark task cost, and
  wall time. Unrelated benchmark scores are not promoted into this list.
- **Value (separate bases)** – benchmark task value and token-price value are
  separate datasets; neither treats $/Mtok as $/task.
- **Change Log** – new / updated / removed entries across all sources.
- **Sources** – per-source health, last run, consecutive errors (auto-pauses
  after 4 failures).

## Evidence and recommendation design

Every source row is assigned an evidence lane before it can affect a score.
The important distinction is between an actual benchmark measurement and a
supporting signal:

| Evidence lane | Examples | Used for |
|---|---|---|
| Coding Agent | AA Coding Agent leaderboard | General coder and complex code |
| Coding support | LiveBench coding, SWE-bench, Aider, EvalPlus | Supporting evidence |
| Agentic / tool use | Terminal-Bench, DeepSWE, BFCL | Research and complex-code evidence |
| Visual / frontend | LMArena vision and WebDev boards | UI coder |
| Intelligence / reasoning | AA Intelligence, LiveBench reasoning | Research and supporting evidence |

Repeated rows from one benchmark are aggregated before they contribute. A
singleton benchmark cohort is treated as missing evidence rather than being
given a synthetic score of 50. Every recommendation carries its measurement
type, evidence coverage, source names, and warnings.

The role profiles and OpenCode workload are configured in `config.json`.
The default workload uses 120k input tokens and 8k output tokens per turn.
Token price and benchmark task cost are never placed in the same price tier.

## The EST estimator

- `CodingAgentIndex ≈ 0.01417 × IntelligenceIndex − 0.2089` (r = 0.898)
- cross-check: `≈ 0.01206 × codingIndex − 0.3022` (r = 0.883)
- both regressions are recomputed live from current matched pairs as a
  diagnostic; config values are canonical.
- matching rules: harness prefix stripped, effort suffix extracted,
  "Fallback" names excluded unless the coding entry says "(with fallback)",
  exact-effort variant required, non-estimated variants preferred.
- family adjustments apply only to predictions. Observed Coding Agent and
  model-index values are never changed by a family heuristic.
- estimates above the regression's training range are capped at 75 points and
  flagged `extrapolated` with a wider ±10-point band.
- validation: Qwen3.8 Max predicted 0.614 → actual 0.587.

## Sources (verified live 2026-08-13)

| Source | Endpoint | Notes |
|---|---|---|
| AA Coding Agents | `artificialanalysis.ai/agents/coding-agents` | RSC payload in HTML, regex window extraction; KNOWN-GOOD sanity-checked |
| AA Models | `artificialanalysis.ai/leaderboards/models` | 4.8 MB HTML, ~600 models |
| AA Changelog | `artificialanalysis.ai/changelog` | new-article signal |
| LMArena | `lmarena.ai/leaderboard` | Elo entries embedded in RSC payload (11 arenas) |
| LiveBench | `livebench.ai/table_2026_06_25.csv` + `categories_*.json` | release date auto-discovered from site JS |
| SWE-bench | `swebench.com` | `<script id="leaderboard-data">` JSON, resolve-rate computed from per-instance details |
| aider polyglot | `aider.chat/docs/leaderboards/` | HTML table parse |
| EvalPlus | `evalplus.github.io/results.json` | HumanEval+/MBPP+ pass@1 mean |
| HF Open LLM | datasets-server `open-llm-leaderboard/contents` | chat + pretrained rows, flagged filtered, top 300 |
| OpenRouter | `openrouter.ai/api/v1/models` | pricing / context / created (market data, no score) |
| DeepSeek official | `api-docs.deepseek.com/quick_start/pricing` | first-party peak/off-peak pricing (market data) |
| Terminal-Bench | `tbench.ai` | accuracy JSON embedded in RSC payload |
| DeepSWE | `deepswe.datacurve.ai/artifacts/v1/leaderboard.json` | task pass-any rate, CIs, cost |
| BFCL (Gorilla) | `gorilla.cs.berkeley.edu/data_overall.csv` | tool-use (informational, not in composite weights) |

Scale SEAL is disabled by default (`scale_seal.enabled=false`) — its data is
loaded client-side from an undiscoverable endpoint; re-enable after wiring a
source module in `model_tracker/sources/`.

All sources are best-effort: 403/429 → exponential backoff with jitter;
repeated failures pause the source (resume after 4× interval); everything is
cached on disk per-URL. Personal use — respect each site's ToS.

## Prior analysis findings (live in dashboard)

- Value king: **Codex - GPT-5.6 Luna (max)** 0.587 @ $0.31/task
  (raw ratio king: DeepSeek V4 Flash at $0.07/task).
- Best workhorses: **Grok 4.5 (high)** 0.644 @ $2.59; **GPT-5.6 Terra (max)**
  0.623 @ $2.21.
- OpenRouter: pass-through pricing + 5.5% credit fee, no volume discounts,
  not AA-benchmarked, worse prompt-caching for agents; direct providers
  (DeepSeek official, DeepInfra, CoreWeave, Novita, Cerebras, Groq) are
  usually cheaper/faster. First-party for closed frontier models.
- DeepSeek repriced 2026-08-16 (16:00 UTC): flat rates replaced by
  peak/off-peak billing. V4 Pro went from $0.435/$0.87 (in/out) to
  $0.66/$1.98 off-peak and $1.32/$3.96 at peak (01:00–04:00 and
  06:00–10:00 UTC) — up to 4.55× on output, 12× on cache hits. Third-party
  hosts lagged the change; the `deepseek` source tracks the official rates.

## Layout

```
model_tracker/
  aa.py            AA page parsers (proven regex-window extraction)
  http.py          fetch + retry/backoff + disk cache
  store.py         SQLite snapshots / rows / changes / scores
  normalize.py     model identity resolution (family+version canon keys)
  estimator.py     EST regressions, matching rules, outlier adjustments
  composite.py     evidence lanes, benchmark aggregation, meta summary
  recommendations.py role-specific scoring and OpenCode cost model
  validation.py    fail-closed source snapshot validation
  engine.py        orchestration: scrape → diff → estimate → score → alert
  scheduler.py     per-source threads, jitter, backoff, pause
  alerts.py        console banner + Windows toast
  web.py           FastAPI dashboard API
  cli.py           run-once / serve / summary / scrape
static/            dashboard UI (vanilla JS, sortable tables)
config.json        weights, intervals, EST params, workloads, alerts
tests/             replayable scoring, recommendation, and source validation tests
scripts/verify_aa.py   KNOWN-GOOD regression check for the AA scrapers
data/              tracker.db + http cache (gitignored)
```

## Config knobs (`config.json`)

- `weights` – composite category weights
- `normalization.mode` – `minmax` (default) or `percentile`
- `est.*` – regression coefficients, ±band, cap, agreement threshold
- `workloads.opencode_turn` – token assumptions and per-role budgets
- `sources.<name>.interval_min` / `.enabled`
- `alerts.desktop_toast` / `console_banner` / `max_consecutive_errors`
- `known_underperform` / `known_overperform` – family adjustment lists
