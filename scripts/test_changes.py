import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from model_tracker.store import Store
from model_tracker.normalize import canon

with tempfile.TemporaryDirectory() as tmp:
    store = Store(pathlib.Path(tmp) / "test.db")
    s1 = store.begin_snapshot("aa_coding", True)
    store.insert_rows(s1, "aa_coding", [
        {"kind": "coding_index", "slug": "claude-code-opus-5-xhigh", "name": "Claude Code - Opus 5 (xhigh)", "score": 66.74, "extra": {}},
    ])
    store.finish_snapshot(s1, 1)
    s2 = store.begin_snapshot("aa_coding", True)
    store.insert_rows(s2, "aa_coding", [
        {"kind": "coding_index", "slug": "claude-code-opus-5-xhigh", "name": "Claude Code - Opus 5 (xhigh)", "score": 67.10, "extra": {}},
        {"kind": "coding_index", "slug": "codex-gpt-5-6-nova-max", "name": "Codex - GPT-5.6 Nova (max)", "score": 70.00, "extra": {}},
    ])
    store.finish_snapshot(s2, 2)
    snaps = store.snapshots_for("aa_coding", 2)
    changes = store.detect_changes("aa_coding", snaps[1], snaps[0])
    for c in changes:
        print(f"  {c['event']:8} {c['name']:35} {c['detail']}")
    assert any(c["event"] == "new" and "Nova" in c["name"] for c in changes)
    assert any(c["event"] == "updated" and "Opus" in c["name"] for c in changes)
    print("change detection OK")
    store.close()
