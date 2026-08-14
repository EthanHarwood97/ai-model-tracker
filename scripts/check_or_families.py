import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from model_tracker.store import Store
from model_tracker.http import load_config

s = Store(load_config()["db_path"])
snap = s.snapshots_for("openrouter", 1)[0]
rows = [dict(r) for r in s.rows_for(snap["id"])]
print("OpenRouter models for the three families:")
for r in rows:
    e = json.loads(r["extra"] or "{}")
    rid = e.get("or_id") or ""
    if any(x in rid for x in ["deepseek", "luna", "kimi", "moonshot"]):
        print(f"  {rid:44} in=${e.get('price_prompt')} out=${e.get('price_completion')} ctx={e.get('context_length')}")
