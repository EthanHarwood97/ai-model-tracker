import logging
import random
import threading
import time
from datetime import datetime, timezone

from .sources import SOURCES

log = logging.getLogger("tracker.scheduler")


class Scheduler:
    def __init__(self, cfg, engine):
        self.cfg = cfg
        self.engine = engine
        self.stop_event = threading.Event()
        self.status = {}
        self.lock = threading.Lock()
        self.threads = []

    def _interval_for(self, name):
        src = self.cfg["sources"].get(name, {})
        return max(10, int(src.get("interval_min", 60))) * 60

    def _source_loop(self, name):
        max_errs = self.cfg.get("alerts", {}).get("max_consecutive_errors", 4)
        consecutive = 0
        while not self.stop_event.is_set():
            src = self.cfg["sources"].get(name, {})
            if not src.get("enabled", True):
                with self.lock:
                    self.status[name] = {"state": "disabled", "last_run": None, "last_ok": None, "consecutive_errors": 0}
                self.stop_event.wait(300)
                continue
            interval = self._interval_for(name)
            jitter = random.uniform(0.85, 1.15)
            wait = interval * jitter if consecutive == 0 else min(interval * jitter, (2 ** consecutive) * interval / 4)
            self.stop_event.wait(wait)
            if self.stop_event.is_set():
                break
            started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                rows, changes = self.engine.run_source(name)
                consecutive = 0
                with self.lock:
                    self.status[name] = {
                        "state": "ok", "last_run": started, "last_ok": started,
                        "rows": len(rows), "new": len([c for c in changes if c["event"] == "new"]),
                        "consecutive_errors": 0,
                    }
                self.engine.compute()
            except Exception as e:
                consecutive += 1
                with self.lock:
                    self.status[name] = {
                        "state": "error", "last_run": started, "error": str(e),
                        "consecutive_errors": consecutive,
                    }
                if consecutive >= max_errs:
                    log.warning("%s failed %d times in a row - pausing", name, consecutive)
                    with self.lock:
                        self.status[name]["state"] = "paused"
                    self.stop_event.wait(interval * 4)
                    consecutive = 0

    def start(self):
        for name in self.engine.cfg["sources"]:
            if name not in SOURCES:
                continue
            t = threading.Thread(target=self._source_loop, args=(name,), daemon=True, name=f"src-{name}")
            t.start()
            self.threads.append(t)

    def stop(self):
        self.stop_event.set()

    def snapshot_status(self):
        with self.lock:
            return {k: dict(v) for k, v in self.status.items()}
