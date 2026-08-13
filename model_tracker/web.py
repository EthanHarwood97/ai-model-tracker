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

    @app.get("/api/views/coding")
    def view_coding():
        rows = [s for s in engine.store.latest_scores() if s["measured"]]
        rows.sort(key=lambda s: -(s["coding_index"] or 0))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/est")
    def view_est():
        rows = [s for s in engine.store.latest_scores() if not s["measured"]]
        rows.sort(key=lambda s: -(s["coding_index"] or 0))
        return [_entity_dict(s) for s in rows]

    @app.get("/api/views/value")
    def view_value():
        rows = [
            s for s in engine.store.latest_scores()
            if s["cost_task"] is not None or s["price_mtok"] is not None
        ]
        rows.sort(key=lambda s: -((s["coding_index"] or 0) / max(s["cost_task"] or 1e9, 1e-9)))
        return [_entity_dict(s) for s in rows]

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

    @app.post("/api/refresh")
    def refresh():
        if not refresh_lock.acquire(blocking=False):
            return JSONResponse({"ok": False, "msg": "refresh already running"}, status_code=409)
        try:
            results, errors, entities = engine.cycle(force=True)
            return {"ok": True, "results": results, "errors": errors, "n_entities": len(entities)}
        finally:
            refresh_lock.release()

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app
