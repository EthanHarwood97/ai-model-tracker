import json
import pathlib
import shutil

from .sources import SOURCES
from .validation import validate_rows

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"


def _serialize_row(r):
    try:
        extra = json.loads(r["extra"]) if r["extra"] else {}
    except Exception:
        extra = {}
    return {
        "kind": r["kind"],
        "slug": r["slug"],
        "name": r["name"],
        "score": r["score"],
        "extra": extra,
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
            try:
                validate_rows(name, rows)
            except ValueError:
                continue
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
    est = sorted(
        [s for s in scores if not s["measured"] and json.loads(s.get("detail") or "{}").get("source") != "livebench"],
        key=lambda s: -(s["coding_index"] or 0),
    )
    livebench = sorted(
        [s for s in scores if json.loads(s.get("detail") or "{}").get("source") == "livebench"],
        key=lambda s: -(s["coding_index"] or 0),
    )
    value_task = [
        s for s in scores
        if s["cost_basis"] == "benchmark_task" and s["cost_task"] is not None
    ]
    value_task.sort(key=lambda s: -((s["coding_index"] or 0) / max(s["cost_task"], 1e-9)))
    value_token = [s for s in scores if s["cost_basis"] == "token_price" and s["price_mtok"] is not None]
    value_token.sort(key=lambda s: -((s["coding_index"] or 0) / max(s["price_mtok"], 1e-9)))
    return {
        "meta": [_entity(s) for s in meta],
        "coding": [_entity(s) for s in coding],
        "est": [_entity(s) for s in est],
        "livebench": [_entity(s) for s in livebench],
        "value_task": [_entity(s) for s in value_task],
        "value_token": [_entity(s) for s in value_token],
        "value": [_entity(s) for s in value_task + value_token],
        "models": [_entity(s) for s in scores],
    }


def _sources(engine):
    out = []
    for s in engine.store.source_status():
        out.append({
            "name": s["source"],
            "state": "ok" if s.get("latest_ok") else "stale" if s.get("last_ok") else "pending",
            "last_ok": s["last_ok"],
            "last_run": s.get("last_run"),
            "row_count": s.get("row_count"),
            "consecutive_errors": s.get("consecutive_errors", 0),
            "last_error": s.get("last_error"),
        })
    return out


def _radar(engine):
    articles = []
    snaps = engine.store.snapshots_for("aa_changelog", 1)
    if snaps:
        for r in engine.store.rows_for(snaps[0]["id"]):
            d = dict(r)
            try:
                extra = json.loads(d.get("extra") or "{}")
            except Exception:
                extra = {}
            articles.append({"title": d["name"], "date": extra.get("date"), "slug": extra.get("slug")})
    new_models = []
    for name in SOURCES:
        if name == "aa_changelog":
            continue
        history = engine.store.snapshots_for(name, 4)
        if len(history) < 2:
            continue
        base_id = history[min(3, len(history) - 1)]["id"]
        old_map = engine.store.row_map(base_id)
        new_map = engine.store.row_map(history[0]["id"])
        for key in new_map:
            if key not in old_map:
                row = new_map[key][0]
                new_models.append({"name": row["name"], "source": name, "ts": history[0]["ts"]})
    new_models = new_models[:15]
    est = [s for s in engine.store.latest_scores() if not s["measured"]]
    est.sort(key=lambda s: -(s["coding_index"] or 0))
    candidates = [
        {"name": s["name"], "coding_index": s["coding_index"], "price_mtok": s["price_mtok"]}
        for s in est[:12]
    ]
    return {"articles": articles[:15], "new_models": new_models, "candidates": candidates}


def build_site(engine, site_dir):
    site = pathlib.Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    payload = _views(engine)
    payload["changes"] = engine.store.recent_changes(200)
    payload["sources"] = _sources(engine)
    payload["radar"] = _radar(engine)
    payload["recommendations"] = engine.recommendations()
    payload["status"] = {
        "last_cycle": engine.last_cycle,
        "latest_ts": engine.store.latest_scores()[0]["ts"] if engine.store.latest_scores() else None,
    }
    (site / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(STATIC_DIR / name, site / name)
    return payload
