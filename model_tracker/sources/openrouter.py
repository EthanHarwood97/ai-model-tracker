import json


def fetch(f):
    r = f.get("https://openrouter.ai/api/v1/models", ttl=21600)
    data = json.loads(r.text)
    rows = []
    for m in data.get("data", []):
        pricing = m.get("pricing") or {}

        def fnum(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        prompt = fnum(pricing.get("prompt"))
        completion = fnum(pricing.get("completion"))
        if prompt is not None:
            prompt = round(prompt * 1e6, 4)
        if completion is not None:
            completion = round(completion * 1e6, 4)
        blended = None
        if prompt is not None and completion is not None:
            blended = round((prompt * 3 + completion) / 4, 4)
        rows.append({
            "kind": "market",
            "name": m.get("id", "?"),
            "slug": None,
            "score": None,
            "extra": {
                "or_id": m.get("id"),
                "or_name": m.get("name"),
                "price_prompt": prompt,
                "price_completion": completion,
                "price_blended": blended,
                "context_length": m.get("context_length"),
                "created": m.get("created"),
                "architecture": m.get("architecture"),
            },
        })
    return rows
