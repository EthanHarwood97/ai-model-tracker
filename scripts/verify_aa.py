import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from model_tracker.http import Fetcher, load_config
from model_tracker.aa import scrape_coding, scrape_models

KNOWN = {
    "Claude Code - Opus 5 (xhigh)": (0.6674, 8.23, 1419),
    "Codex - GPT-5.6 Sol (max)": (0.6657, 7.08, 610),
    "Claude Code - Fable 5 (max) (with fallback)": (0.6585, 11.71, 1403),
    "Grok Build - Grok 4.5 (high)": (0.6444, 2.59, 992),
    "Codex - GPT-5.6 Terra (max)": (0.6228, 2.21, 502),
    "Codex - GPT-5.6 Luna (max)": (0.5866, 0.31, 480),
    "Codex - DeepSeek V4 Flash (max)": (0.5547, 0.07, 877),
    "Opencode - Muse Spark 1.1 (xhigh)": (0.5354, 1.43, 755),
}

cfg = load_config()
f = Fetcher(cfg)

html_coding = f.get("https://artificialanalysis.ai/agents/coding-agents", ttl=3600, force=True).text
rows = scrape_coding(html_coding)
print(f"coding rows: {len(rows)}")

by_name = {r["name"]: r for r in rows}
fail = 0
for label, (exp_score, exp_cost, exp_time) in KNOWN.items():
    r = by_name.get(label)
    if not r:
        print(f"MISSING: {label}")
        fail += 1
        continue
    e = r["extra"]
    ok = (
        abs(e["index_raw"] - exp_score) < 0.001
        and abs(e["cost_usd"] - exp_cost) < 0.01
        and abs(e["wall_time_s"] - exp_time) < 1.5
    )
    print(f"{'OK ' if ok else 'BAD'} {label}: score={e['index_raw']} cost=${e['cost_usd']} time={e['wall_time_s']}s")
    if not ok:
        fail += 1

print("top 10 by score:")
for r in sorted(rows, key=lambda x: -x["score"])[:10]:
    e = r["extra"]
    print(f"  {r['score']:7.3f}  ${e['cost_usd']:>7}  {e['wall_time_s']:>6}s  {r['name']}")

html_models = f.get("https://artificialanalysis.ai/leaderboards/models", ttl=3600, force=True).text
mrows = scrape_models(html_models)
print(f"models rows: {len(mrows)}")
for r in mrows[:3]:
    print("  ", r["name"], r["slug"], r["score"])

print("KNOWN-GOOD FAILURES:", fail)
sys.exit(1 if fail else 0)
