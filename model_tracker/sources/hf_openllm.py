import json
import re
import time

BASE = "https://datasets-server.huggingface.co"

TYPES = ["\U0001f4ac chat models (RLHF, DPO, IFT, ...)", "\U0001f7e2 pretrained"]


def _strip_html(v):
    if not isinstance(v, str):
        return v
    m = re.search(r"<a[^>]*>([^<]+)</a>", v)
    if m:
        return m.group(1).strip()
    return re.sub(r"<[^>]+>", "", v).strip()


def _page(f, where, offset):
    params = {
        "dataset": "open-llm-leaderboard/contents",
        "config": "default",
        "split": "train",
        "where": where,
        "limit": "100",
        "offset": str(offset),
    }
    url = BASE + "/filter?" + "&".join(f"{k}={v}" for k, v in params.items())
    for attempt in range(8):
        r = f.get(url, ttl=86400, force=attempt > 0)
        try:
            data = json.loads(r.text)
        except Exception:
            time.sleep(10 * (attempt + 1))
            continue
        if "rows" in data:
            return data
        err = data.get("error", "")
        if "loading" in err or "index" in err:
            time.sleep(25 * (attempt + 1))
            continue
        return data
    return {"rows": [], "num_rows_total": 0}


def _collect(f, where, cap=2000):
    first = _page(f, where, 0)
    rows_data = list(first.get("rows") or [])
    total = first.get("num_rows_total", len(rows_data)) or 0
    total = min(total, cap)
    offset = len(rows_data)
    while offset < total:
        page = _page(f, where, offset)
        got = page.get("rows") or []
        if not got:
            break
        rows_data.extend(got)
        offset += len(got)
    return rows_data


def fetch(f):
    rows_data = []
    for t in TYPES:
        where = f'"Type"=\'{t}\''
        try:
            rows_data.extend(_collect(f, where))
        except Exception:
            continue
    by_model = {}
    for rec in rows_data:
        row = rec.get("row") or {}
        if row.get("Flagged"):
            continue
        model = _strip_html(row.get("Model"))
        if not model:
            continue
        avg = row.get("Average \u2b06\ufe0f")
        if avg is None:
            continue
        prev = by_model.get(model)
        if prev is None or avg > prev["score"]:
            by_model[model] = {
                "kind": "hf_openllm",
                "name": model,
                "slug": None,
                "score": round(float(avg), 2),
                "extra": {
                    "fullname": row.get("fullname"),
                    "architecture": row.get("Architecture"),
                    "params_b": row.get("#Params (B)"),
                    "precision": row.get("Precision"),
                    "flagged": row.get("Flagged"),
                    "type": t,
                },
            }
    out = sorted(by_model.values(), key=lambda r: -r["score"])
    return out[:300]
