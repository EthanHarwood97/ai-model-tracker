import json
import pathlib
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "static"


def _entity_dict(s):
    d = dict(s)
    d["components"] = json.loads(d.get("components") or "{}")
    d["detail"] = json.loads(d.get("detail") or "{}")
    return d


def create_app(engine, scheduler=None):
    app = FastAPI(title="AI Model Score Tracker")
    refresh_lock = threading.Lock()

    @app.get("/api/views/meta")
    def view_meta():
        rows = [s for s in engine.store.latest_scores() if s["meta"] is not None]
        rows.sort(key=lambda s: -s["meta"])
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/models")
    def view_models():
        rows = engine.store.latest_scores()
        rows.sort(key=lambda s: (-(s["meta"] or 0), -(s["coding_index"] or 0), s["name"]))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/coding")
    def view_coding():
        rows = [s for s in engine.store.latest_scores() if s["measured"]]
        rows.sort(key=lambda s: -(s["coding_index"] or 0))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/est")
    def view_est():
        rows = [
            s for s in engine.store.latest_scores()
            if not s["measured"] and (json.loads(s.get("detail") or "{}").get("source") != "livebench")
        ]
        rows.sort(key=lambda s: -(s["coding_index"] or 0))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/livebench")
    def view_livebench():
        rows = [
            s for s in engine.store.latest_scores()
            if json.loads(s.get("detail") or "{}").get("source") == "livebench"
        ]
        rows.sort(key=lambda s: -(s["coding_index"] or 0))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/value")
    def view_value():
        rows = [
            s for s in engine.store.latest_scores()
            if s["cost_task"] is not None or s["price_mtok"] is not None
        ]
        rows.sort(key=lambda s: (
            0 if s["cost_basis"] == "benchmark_task" else 1,
            -((s["coding_index"] or 0) / max(s["cost_task"], 1e-9))
            if s["cost_basis"] == "benchmark_task" and s["cost_task"] is not None
            else -((s["coding_index"] or 0) / max(s["price_mtok"], 1e-9))
            if s["price_mtok"] is not None else 0,
        ))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/value-task")
    def view_value_task():
        rows = [s for s in engine.store.latest_scores() if s["cost_basis"] == "benchmark_task" and s["cost_task"] is not None]
        rows.sort(key=lambda s: -((s["coding_index"] or 0) / max(s["cost_task"], 1e-9)))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/value-token")
    def view_value_token():
        rows = [s for s in engine.store.latest_scores() if s["cost_basis"] == "token_price" and s["price_mtok"] is not None]
        rows.sort(key=lambda s: -((s["coding_index"] or 0) / max(s["price_mtok"], 1e-9)))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/recommendations")
    def recommendations():
        return engine.recommendations()

    @app.get("/api/changes")
    def changes():
        return engine.store.recent_changes(200)

    @app.get("/api/status")
    def status():
        sched = scheduler.snapshot_status() if scheduler else {}
        return {
            "scheduler": sched,
            "last_cycle": engine.last_cycle,
            "sources": engine.store.source_status(),
            "latest_ts": engine.store.latest_scores()[0]["ts"] if engine.store.latest_scores() else None,
        }

    @app.get("/api/radar")
    def radar():
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
        new_models = [
            {"name": c["name"], "source": c["source"], "ts": c["ts"]}
            for c in engine.store.recent_changes(120) if c["event"] == "new"
        ]
        est = [s for s in engine.store.latest_scores() if not s["measured"]]
        est.sort(key=lambda s: -(s["coding_index"] or 0))
        candidates = [
            {"name": s["name"], "coding_index": s["coding_index"], "price_mtok": s["price_mtok"]}
            for s in est[:12]
        ]
        return {"articles": articles[:15], "new_models": new_models[:15], "candidates": candidates}

    @app.post("/api/refresh")
    def refresh():
        if not refresh_lock.acquire(blocking=False):
            return JSONResponse({"ok": False, "msg": "refresh already running"}, status_code=409)
        try:
            results, errors, entities = engine.cycle(force=True)
            return {"ok": not errors, "results": results, "errors": errors, "n_entities": len(entities)}
        finally:
            refresh_lock.release()

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app
