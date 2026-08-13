import json
import pathlib
import shutil

from .sources import SOURCES

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"


def _serialize_row(r):
    return {
        "kind": r["kind"],
        "slug": r["slug"],
        "name": r["name"],
        "score": r["score"],
        "extra": r["extra"] or {},
    }


def import_history(store, snapshots_dir):
    base = pathlib.Path(snapshots_dir)
    if not base.is_dir():
        return 0
    count = 0
    for name in SOURCES:
        d = base / name
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows = data.get("rows") or []
            snap = store.begin_snapshot(name, True, ts=data.get("ts"))
            store.insert_rows(snap, name, rows)
            store.finish_snapshot(snap, len(rows))
            count += 1
    return count


def export_snapshots(store, snapshots_dir, skip_unchanged=True):
    base = pathlib.Path(snapshots_dir)
    base.mkdir(parents=True, exist_ok=True)
    written = 0
    for name in SOURCES:
        snaps = store.snapshots_for(name, 1)
        if not snaps:
            continue
        snap = snaps[0]
        rows = [_serialize_row(r) for r in store.rows_for(snap["id"])]
        d = base / name
        d.mkdir(exist_ok=True)
        existing = sorted(d.glob("*.json"))
        if skip_unchanged and existing:
            try:
                last = json.loads(existing[-1].read_text(encoding="utf-8"))
                if (last.get("rows") or []) == rows:
                    continue
            except Exception:
                pass
        fname = snap["ts"].replace(":", "-") + ".json"
        payload = {"source": name, "ts": snap["ts"], "rows": rows}
        (d / fname).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written += 1
    return written


def _entity(s):
    d = dict(s)
    d["components"] = json.loads(d.get("components") or "{}")
    d["detail"] = json.loads(d.get("detail") or "{}")
    return d


def _views(engine):
    scores = engine.store.latest_scores()
    meta = sorted([s for s in scores if s["meta"] is not None], key=lambda s: -s["meta"])
    coding = sorted([s for s in scores if s["measured"]], key=lambda s: -(s["coding_index"] or 0))
    est = sorted([s for s in scores if not s["measured"]], key=lambda s: -(s["coding_index"] or 0))
    value = [
        s for s in scores
        if s["cost_task"] is not None or s["price_mtok"] is not None
    ]
    value.sort(key=lambda s: -((s["coding_index"] or 0) / max(s["cost_task"] or 1e9, 1e-9)))
    return {
        "meta": [_entity(s) for s in meta],
        "coding": [_entity(s) for s in coding],
        "est": [_entity(s) for s in est],
        "value": [_entity(s) for s in value],
    }


def _sources(engine):
    out = []
    for s in engine.store.source_status():
        out.append({
            "name": s["source"],
            "state": "ok" if s["ok_count"] > 0 else "pending",
            "last_ok": s["last_ok"],
            "row_count": None,
            "consecutive_errors": 0,
            "last_error": None,
        })
    return out


def build_site(engine, site_dir):
    site = pathlib.Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    payload = _views(engine)
    payload["changes"] = engine.store.recent_changes(200)
    payload["sources"] = _sources(engine)
    payload["status"] = {
        "last_cycle": engine.last_cycle,
        "latest_ts": engine.store.latest_scores()[0]["ts"] if engine.store.latest_scores() else None,
    }
    (site / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(STATIC_DIR / name, site / name)
    return payload
