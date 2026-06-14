from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.logging_config import setup_logging

logger = setup_logging(__name__)


class FeedbackStore:
    def __init__(self, db_path: str | Path = "data/feedback.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                answer TEXT,
                feature_detected TEXT,
                thumbs_up BOOLEAN,
                timestamp TEXT,
                session_id TEXT
            )
        """)
        conn.commit()
        conn.close()

    def store_feedback(
        self,
        query: str,
        answer: str,
        feature: str,
        thumbs_up: bool,
        session_id: str,
    ) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT INTO feedback (query, answer, feature_detected, thumbs_up, timestamp, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                query,
                answer,
                feature,
                int(thumbs_up),
                datetime.now(timezone.utc).isoformat(),
                session_id,
            ),
        )
        conn.commit()
        conn.close()

    def get_all(
        self,
        user: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if user is None:
            logger.warning("Feedback access denied: no authenticated user")
            return []
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, query, answer, feature_detected, thumbs_up, timestamp, session_id "
            "FROM feedback ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
