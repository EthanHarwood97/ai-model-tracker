import pathlib
import tempfile
import unittest
from unittest.mock import patch

from model_tracker.engine import Engine
from model_tracker.http import Fetcher
from model_tracker.store import Store


class PipelineTests(unittest.TestCase):
    def test_force_refresh_reaches_source_fetcher(self):
        seen = []

        def fetch(fake_fetcher):
            seen.append(fake_fetcher.force_refresh)
            return [{"kind": "generic", "name": "Model", "score": 50, "extra": {}}]

        cfg = {
            "http": {},
            "sources": {"test_source": {"enabled": True}},
            "alerts": {"desktop_toast": False},
        }
        with tempfile.TemporaryDirectory() as tmp, patch("model_tracker.engine.SOURCES", {"test_source": fetch}):
            store = Store(pathlib.Path(tmp) / "test.db")
            engine = Engine(cfg, store, Fetcher({"http": {}, "cache_dir": pathlib.Path(tmp) / "cache"}))
            engine.run_source("test_source", force=True)
            self.assertEqual(seen, [True])
            self.assertFalse(engine.fetcher.force_refresh)
            store.close()

    def test_change_detection_keeps_benchmark_kinds_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(pathlib.Path(tmp) / "test.db")
            first = store.begin_snapshot("livebench", True)
            store.insert_rows(first, "livebench", [
                {"kind": "livebench_coding", "name": "Model", "score": 50, "extra": {}},
                {"kind": "livebench_agentic", "name": "Model", "score": 30, "extra": {}},
            ])
            store.finish_snapshot(first, 2)
            second = store.begin_snapshot("livebench", True)
            store.insert_rows(second, "livebench", [
                {"kind": "livebench_coding", "name": "Model", "score": 60, "extra": {}},
                {"kind": "livebench_agentic", "name": "Model", "score": 40, "extra": {}},
            ])
            store.finish_snapshot(second, 2)
            snapshots = store.snapshots_for("livebench", 2)
            changes = store.detect_changes("livebench", snapshots[1], snapshots[0])
            self.assertEqual({change["kind"] for change in changes}, {"livebench_coding", "livebench_agentic"})
            store.close()


if __name__ == "__main__":
    unittest.main()
