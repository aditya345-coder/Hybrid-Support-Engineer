import json
import sqlite3
import tempfile
from pathlib import Path

from middleware.feedback import FeedbackStore


def test_store_and_retrieve_feedback():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "feedback.db"
        store = FeedbackStore(db_path)

        store.store_feedback(
            query="How do I configure CORS?",
            answer="Use CORSMiddleware",
            feature="middleware",
            thumbs_up=True,
            session_id="session-1",
        )

        store.store_feedback(
            query="How to bake a cake?",
            answer="I cannot answer that",
            feature="General",
            thumbs_up=False,
            session_id="session-2",
        )

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT * FROM feedback ORDER BY id").fetchall()
        conn.close()

        assert len(rows) == 2

        row1 = rows[0]
        assert row1[1] == "How do I configure CORS?"
        assert row1[2] == "Use CORSMiddleware"
        assert row1[3] == "middleware"
        assert row1[4] == 1
        assert row1[6] == "session-1"

        row2 = rows[1]
        assert row2[1] == "How to bake a cake?"
        assert row2[4] == 0
        assert row2[6] == "session-2"


def test_init_creates_table():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        _store = FeedbackStore(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        assert cursor.fetchone() is not None
        conn.close()


def test_get_all_feedback():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "feedback.db"
        store = FeedbackStore(db_path)

        store.store_feedback("q1", "a1", "f1", True, "s1")
        store.store_feedback("q2", "a2", "f2", False, "s2")

        all_items = store.get_all(user={"sub": "test-user", "permissions": []})
        assert len(all_items) == 2


def test_json_serializable():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "feedback.db"
        store = FeedbackStore(db_path)

        store.store_feedback("q1", "a1", "f1", True, "s1")
        all_items = store.get_all(user={"sub": "test-user", "permissions": []})

        json.dumps(all_items)
