import json


def fetch(f):
    r = f.get("https://evalplus.github.io/results.json", ttl=86400)
    data = json.loads(r.text)
    rows = []
    for name, entry in data.items():
        pass1 = entry.get("pass@1") or {}
        vals = [v for v in (pass1.get("humaneval+"), pass1.get("mbpp+")) if v is not None]
        if not vals:
            continue
        rows.append({
            "kind": "evalplus",
            "name": name,
            "slug": None,
            "score": round(sum(vals) / len(vals), 2),
            "extra": {
                "humaneval_plus": pass1.get("humaneval+"),
                "mbpp_plus": pass1.get("mbpp+"),
                "humaneval": pass1.get("humaneval"),
                "mbpp": pass1.get("mbpp"),
                "size_b": entry.get("size"),
                "open_data": entry.get("open-data"),
            },
        })
    return rows
