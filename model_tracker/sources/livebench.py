import csv
import io
import json
import re


def _latest_release(f, cfg):
    try:
        r = f.get("https://livebench.ai/static/js/main.d58a98ac.js", ttl=86400)
        m = re.search(r'const pe=\[((?:"[^"]+",?)+)\]', r.text)
        if m:
            dates = re.findall(r'"([\d-]+)"', m.group(1))
            if dates:
                return dates[-1].replace("-", "_")
    except Exception:
        pass
    return cfg.get("sources", {}).get("livebench", {}).get("release", "2026_06_25")


def _categories(f, release):
    try:
        r = f.get(f"https://livebench.ai/categories_{release}.json", ttl=86400)
        return json.loads(r.text)
    except Exception:
        return {}


def fetch(f):
    release = _latest_release(f, f.config)
    cats = _categories(f, release)
    r = f.get(f"https://livebench.ai/table_{release}.csv", ttl=86400)
    reader = csv.DictReader(io.StringIO(r.text))
    header = [h for h in (reader.fieldnames or [])]
    coding_cols = set(cats.get("Coding", []) + cats.get("Agentic Coding", []))
    reasoning_cols = set(cats.get("Reasoning", []))
    agentic_cols = set(cats.get("Agentic Coding", []))
    rows = []
    for rec in reader:
        model = rec.get("model")
        if not model:
            continue
        vals = {}
        for col in header:
            if col == "model":
                continue
            raw = rec.get(col)
            if raw in (None, ""):
                continue
            try:
                vals[col] = float(raw)
            except ValueError:
                continue
        allv = list(vals.values())

        def mean_of(cols):
            subset = [v for c, v in vals.items() if c in cols]
            return round(sum(subset) / len(subset), 2) if subset else None

        def emit(kind, value):
            if value is None:
                return
            rows.append({"kind": kind, "name": model, "slug": None, "score": value, "extra": {}})

        emit("livebench_global", round(sum(allv) / len(allv), 2) if allv else None)
        emit("livebench_coding", mean_of(coding_cols))
        emit("livebench_agentic", mean_of(agentic_cols))
        emit("livebench_reasoning", mean_of(reasoning_cols))
    return rows
