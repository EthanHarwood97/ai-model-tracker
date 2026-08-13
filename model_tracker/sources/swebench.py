import json
import re


def fetch(f):
    r = f.get("https://www.swebench.com/")
    m = re.search(r'<script type="application/json" id="leaderboard-data">([\s\S]*?)</script>', r.text)
    if not m:
        return []
    try:
        sections = json.loads(m.group(1))
    except Exception:
        return []
    rows = []
    seen = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        sname = str(section.get("name") or "main").lower().replace(" ", "_")
        for res in section.get("results", []):
            name = res.get("name") or res.get("model_display")
            if not name:
                continue
            details = res.get("per_instance_details") or {}
            resolved = sum(1 for d in details.values() if isinstance(d, dict) and d.get("resolved"))
            total = len(details)
            if total == 0:
                score = None
            else:
                score = round(100.0 * resolved / total, 2)
            key = (sname, name)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "kind": f"swebench_{sname}",
                "name": name,
                "slug": None,
                "score": score,
                "extra": {
                    "model_display": res.get("model_display"),
                    "organization": res.get("model_org"),
                    "agent": res.get("agent"),
                    "release_date": res.get("model_release_date"),
                    "os_model": res.get("os_model"),
                    "n_instances": total,
                    "n_resolved": resolved,
                    "avg_cost": res.get("instance_cost"),
                },
            })
    return rows
