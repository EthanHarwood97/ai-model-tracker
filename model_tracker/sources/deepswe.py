import json


def fetch(f):
    r = f.get("https://deepswe.datacurve.ai/artifacts/v1/leaderboard.json", ttl=86400)
    data = json.loads(r.text)
    rows = []
    for row in data.get("rows", []):
        model = row.get("model")
        if not model:
            continue
        rate = row.get("task_pass_any_rate") if row.get("task_pass_any_rate") is not None else row.get("pass_at_4")
        if rate is None:
            continue
        rows.append({
            "kind": "deepswe",
            "name": model,
            "slug": None,
            "score": round(rate * 100, 2),
            "extra": {
                "config": row.get("config"),
                "reasoning_efforts": row.get("reasoning_efforts"),
                "pass_at_1": row.get("pass_at_1"),
                "pass_at_4": row.get("pass_at_4"),
                "task_pass_any_rate": row.get("task_pass_any_rate"),
                "median_cost_usd": row.get("median_cost_usd"),
                "ci_lo": row.get("ci_lo"),
                "ci_hi": row.get("ci_hi"),
                "n_tasks_in_set": data.get("n_tasks_in_set"),
            },
        })
    return rows
