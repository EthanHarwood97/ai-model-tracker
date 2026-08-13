import csv
import io
import re


def fetch(f):
    r = f.get("https://gorilla.cs.berkeley.edu/data_overall.csv", ttl=86400)
    reader = csv.DictReader(io.StringIO(r.text))
    header = reader.fieldnames or []
    score_col = None
    for h in header:
        if re.search(r"overall", h, re.IGNORECASE) and not re.search(r"error", h, re.IGNORECASE):
            score_col = h
            break
    if score_col is None and header:
        score_col = header[1] if len(header) > 1 else None
    model_col = None
    for h in header:
        if re.search(r"model|organization|rank", h, re.IGNORECASE) and "model" in h.lower():
            model_col = h
            break
    if model_col is None and header:
        model_col = header[0]
    rows = []
    for rec in reader:
        name = rec.get(model_col) if model_col else None
        if not name:
            continue
        raw = rec.get(score_col) if score_col else None
        if raw in (None, "", "N/A"):
            continue
        try:
            score = float(raw.replace("%", ""))
        except ValueError:
            continue
        rows.append({
            "kind": "gorilla",
            "name": name.strip(),
            "slug": None,
            "score": round(score, 2),
            "extra": {"col": score_col},
        })
    return rows
