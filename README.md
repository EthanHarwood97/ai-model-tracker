# AI Model Score Tracker

Self-hosted, multi-source tracker for AI model scores. Polls 13 leaderboards
(primary: Artificial Analysis), computes a weighted **meta score** for every
model, and produces **EST** (estimated) coding-agent scores for models that
have an Intelligence Index but no coding-agent benchmark yet.

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

- **Meta Ranking** – weighted composite across sources, sortable, with
  measured/estimated + NEW badges and a confidence band.
- **Coding Leaderboard** – AA Coding Agent Index (DeepSWE + Terminal-Bench v2
  + SWE-Atlas-QnA), cost/task and wall time.
- **EST · Unbenchmarked** – regression estimates with ±0.06 band, dual
  regression agreement check, quirky-family (DeepSeek/GLM/Kimi) warnings.
- **Value ($)** – coding index per dollar (per-task cost for measured, blended
  $/Mtok for estimates).
- **Change Log** – new / updated / removed entries across all sources.
- **Sources** – per-source health, last run, consecutive errors (auto-pauses
  after 4 failures).

## Meta score design

Every source is normalized to 0–100 (min-max within the source's latest
snapshot), then combined with configurable weights (`config.json`):

| Category | Weight | Sources |
|---|---|---|
| Coding-agent skill | 35% | AA coding index (measured) **or** EST estimate (flagged) |
| General intelligence | 25% | AA Intelligence Index |
| Code correctness | 20% | LiveBench coding, SWE-bench verified, EvalPlus, aider polyglot |
| Human preference | 10% | LMArena arenas (text, code, vision, search, document…) |
| Agentic / terminal | 10% | Terminal-Bench, DeepSWE |

Weights renormalize over available categories; each composite records
`n_sources`, last-update per source, and a confidence band (component
dispersion, plus the ±0.06 EST error propagated when the coding score is an
estimate).

## The EST estimator

- `CodingAgentIndex ≈ 0.01417 × IntelligenceIndex − 0.2089` (r = 0.898)
- cross-check: `≈ 0.01206 × codingIndex − 0.3022` (r = 0.883)
- both regressions are recomputed live from current matched pairs as a
  diagnostic; config values are canonical.
- matching rules: harness prefix stripped, effort suffix extracted,
  "Fallback" names excluded unless the coding entry says "(with fallback)",
  exact-effort variant required, non-estimated variants preferred.
- family adjustments: −0.10 for GLM-5.2 / Kimi K2.6 / DeepSeek V4 Pro /
  Gemini 3.6 Flash / Opus 4.7 family; +0.06 for Grok 4.5 and GPT-5.6.
- estimates above the regression's training range are capped at 0.75 and
  flagged `extrapolated` with a wider ±0.10 band (legacy high-intelligence
  models would otherwise saturate at 1.0).
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

## Layout

```
model_tracker/
  aa.py            AA page parsers (proven regex-window extraction)
  http.py          fetch + retry/backoff + disk cache
  store.py         SQLite snapshots / rows / changes / scores
  normalize.py     model identity resolution (family+version canon keys)
  estimator.py     EST regressions, matching rules, outlier adjustments
  composite.py     normalization + weighted meta score + bands
  engine.py        orchestration: scrape → diff → estimate → score → alert
  scheduler.py     per-source threads, jitter, backoff, pause
  alerts.py        console banner + Windows toast
  web.py           FastAPI dashboard API
  cli.py           run-once / serve / summary / scrape
static/            dashboard UI (vanilla JS, sortable tables)
config.json        weights, intervals, EST params, alerts
scripts/verify_aa.py   KNOWN-GOOD regression check for the AA scrapers
data/              tracker.db + http cache (gitignored)
```

## Config knobs (`config.json`)

- `weights` – composite category weights
- `normalization.mode` – `minmax` (default) or `percentile`
- `est.*` – regression coefficients, ±band, cap, agreement threshold
- `sources.<name>.interval_min` / `.enabled`
- `alerts.desktop_toast` / `console_banner` / `max_consecutive_errors`
- `known_underperform` / `known_overperform` – family adjustment lists
