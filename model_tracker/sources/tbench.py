import re


def fetch(f):
    r = f.get("https://www.tbench.ai/")
    text = r.text.replace(r"\"", '"')
    rows = []
    seen = {}
    for m in re.finditer(
        r'"agent":"((?:[^"\\]|\\.)*)","model":"((?:[^"\\]|\\.)*)","accuracy":([\d.eE+-]+)(?:,"accuracyLabel":"[^"]*")?,"stderr":([\d.eE+-]+)',
        text,
    ):
        agent = m.group(1)
        model = m.group(2)
        acc = float(m.group(3))
        key = (agent, model)
        if key in seen and seen[key] >= acc:
            continue
        seen[key] = acc
    for (agent, model), acc in seen.items():
        rows.append({
            "kind": "tbench",
            "name": f"{agent} - {model}",
            "slug": None,
            "score": round(acc * 100, 2),
            "extra": {"agent": agent, "model": model},
        })
    return rows
