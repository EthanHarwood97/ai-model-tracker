import json
import pathlib
import sqlite3
import threading
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  ts TEXT NOT NULL,
  ok INTEGER NOT NULL,
  http_status INTEGER,
  bytes INTEGER,
  error TEXT,
  row_count INTEGER
);
CREATE TABLE IF NOT EXISTS source_rows(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER NOT NULL,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  slug TEXT,
  name TEXT NOT NULL,
  score REAL,
  extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_rows_snap ON source_rows(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_rows_slug ON source_rows(slug);
CREATE TABLE IF NOT EXISTS changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  slug TEXT,
  name TEXT NOT NULL,
  event TEXT NOT NULL,
  detail TEXT,
  alerted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_changes_ts ON changes(ts);
CREATE TABLE IF NOT EXISTS scores(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  meta REAL,
  meta_min REAL,
  meta_max REAL,
  measured INTEGER,
  n_sources INTEGER,
  components TEXT,
  coding_index REAL,
  intelligence REAL,
  price_mtok REAL,
  cost_task REAL,
  harness TEXT,
  wall_time_s REAL,
  context_window REAL,
  output_speed REAL,
  vision REAL,
  vision_mmmu REAL,
  vision_arena REAL,
  speed REAL,
  time_to_first_answer REAL,
  is_new INTEGER DEFAULT 0,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_scores_ts ON scores(ts);
"""


class Store:
    def __init__(self, db_path):
        self.path = pathlib.Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        for column, kind in (("harness", "TEXT"), ("wall_time_s", "REAL"), ("context_window", "REAL"), ("output_speed", "REAL"), ("vision", "REAL"), ("vision_mmmu", "REAL"), ("vision_arena", "REAL"), ("speed", "REAL"), ("time_to_first_answer", "REAL")):
            try:
                self.conn.execute(f"ALTER TABLE scores ADD COLUMN {column} {kind}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()
        self.lock = threading.Lock()

    def close(self):
        self.conn.close()

    def begin_snapshot(self, source, ok, http_status=None, size=None, error=None, ts=None):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO snapshots(source, ts, ok, http_status, bytes, error) VALUES (?,?,?,?,?,?)",
                (source, ts or utcnow(), 1 if ok else 0, http_status, size, error),
            )
            self.conn.commit()
            return cur.lastrowid

    def finish_snapshot(self, snapshot_id, row_count):
        with self.lock:
            self.conn.execute("UPDATE snapshots SET row_count=? WHERE id=?", (row_count, snapshot_id))
            self.conn.commit()

    def insert_rows(self, snapshot_id, source, rows):
        with self.lock:
            payload = [
                (
                    snapshot_id, source, r.get("kind", "generic"), r.get("slug"),
                    r.get("name", "?"), r.get("score"), json.dumps(r.get("extra", {}), ensure_ascii=False),
                )
                for r in rows
            ]
            self.conn.executemany(
                "INSERT INTO source_rows(snapshot_id, source, kind, slug, name, score, extra) VALUES (?,?,?,?,?,?,?)",
                payload,
            )
            self.conn.commit()

    def snapshots_for(self, source, limit=10):
        return self.conn.execute(
            "SELECT * FROM snapshots WHERE source=? AND ok=1 ORDER BY id DESC LIMIT ?",
            (source, limit),
        ).fetchall()

    def rows_for(self, snapshot_id):
        return self.conn.execute(
            "SELECT * FROM source_rows WHERE snapshot_id=?", (snapshot_id,)
        ).fetchall()

    def row_map(self, snapshot_id):
        out = {}
        for r in self.rows_for(snapshot_id):
            key = r["slug"] or r["name"]
            out.setdefault(key, []).append(r)
        return out

    def detect_changes(self, source, old_snapshot, new_snapshot, threshold=0.01):
        changes = []
        old_map = self.row_map(old_snapshot["id"])
        new_map = self.row_map(new_snapshot["id"])
        for key in new_map:
            if key not in old_map:
                r = new_map[key][0]
                changes.append(dict(source=source, kind=r["kind"], slug=key, name=r["name"], event="new",
                                    detail=f"first seen in {source}/{r['kind']}"))
            else:
                o, n = old_map[key][0], new_map[key][0]
                if o["score"] is not None and n["score"] is not None and abs(n["score"] - o["score"]) >= threshold:
                    changes.append(dict(source=source, kind=n["kind"], slug=key, name=n["name"], event="updated",
                                        detail=f"{o['score']:.3f} -> {n['score']:.3f}"))
        for key in old_map:
            if key not in new_map:
                r = old_map[key][0]
                changes.append(dict(source=source, kind=r["kind"], slug=key, name=r["name"], event="removed",
                                    detail=f"gone from {source}/{r['kind']}"))
        return changes

    def insert_changes(self, changes, alerted=False):
        with self.lock:
            ts = utcnow()
            payload = [
                (ts, c["source"], c["kind"], c["slug"], c["name"], c["event"], c["detail"], 1 if alerted else 0)
                for c in changes
            ]
            if payload:
                self.conn.executemany(
                    "INSERT INTO changes(ts, source, kind, slug, name, event, detail, alerted) VALUES (?,?,?,?,?,?,?,?)",
                    payload,
                )
                self.conn.commit()
            return payload

    def replace_scores(self, score_rows):
        with self.lock:
            ts = utcnow()
            self.conn.execute("DELETE FROM scores")
            payload = []
            for s in score_rows:
                payload.append((
                    ts, s["slug"], s["name"], s["meta"], s.get("meta_min"), s.get("meta_max"),
                    1 if s.get("measured") else 0, s.get("n_sources", 0),
                    json.dumps(s.get("components", {}), ensure_ascii=False),
                    s.get("coding_index"), s.get("intelligence"),
                    s.get("price_mtok"), s.get("cost_task"),
                    s.get("harness"), s.get("wall_time_s"),
                    s.get("context_window"), s.get("output_speed"),
                    s.get("vision"), s.get("vision_mmmu"), s.get("vision_arena"),
                    s.get("speed"), s.get("time_to_first_answer"),
                    1 if s.get("is_new") else 0,
                    json.dumps(s.get("detail", {}), ensure_ascii=False),
                ))
            self.conn.executemany(
                "INSERT INTO scores(ts, slug, name, meta, meta_min, meta_max, measured, n_sources, components,"
                " coding_index, intelligence, price_mtok, cost_task, harness, wall_time_s, context_window, output_speed,"
                " vision, vision_mmmu, vision_arena, speed, time_to_first_answer, is_new, detail)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                payload,
            )
            self.conn.commit()
            return ts

    def latest_scores(self):
        ts = self.conn.execute("SELECT MAX(ts) FROM scores").fetchone()[0]
        if not ts:
            return []
        return [dict(r) for r in self.conn.execute("SELECT * FROM scores WHERE ts=?", (ts,)).fetchall()]

    def recent_changes(self, limit=200):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM changes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    def source_status(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT source, MAX(ts) AS last_ok, SUM(ok) AS ok_count, COUNT(*) AS total FROM snapshots GROUP BY source"
        ).fetchall()]

    def unseen_new_slugs(self, source=None):
        q = "SELECT DISTINCT slug FROM changes WHERE event='new'"
        if source:
            q += f" AND source='{source}'"
        return [r[0] for r in self.conn.execute(q).fetchall()]
