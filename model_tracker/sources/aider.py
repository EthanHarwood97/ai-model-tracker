import re


def fetch(f):
    r = f.get("https://aider.chat/docs/leaderboards/")
    text = r.text
    tbody = re.search(r"<tbody>([\s\S]*?)</tbody>", text)
    if not tbody:
        return []
    rows = []
    seen = set()
    for tr in re.finditer(r"<tr[\s\S]*?</tr>", tbody.group(1)):
        block = tr.group(0)
        mm = re.search(r"<span>([^<]+)</span>", block)
        if not mm:
            continue
        model = mm.group(1).strip()
        pm = re.search(r"<span>(\d+(?:\.\d+)?)%</span>", block)
        cm = re.search(r'data-cost="([\d.]+)"', block)
        if not pm:
            continue
        key = model
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "kind": "aider_polyglot",
            "name": model,
            "slug": None,
            "score": float(pm.group(1)),
            "extra": {"cost_per_run_usd": float(cm.group(1)) if cm else None},
        })
    return rows
