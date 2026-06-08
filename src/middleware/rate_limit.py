import threading
from datetime import date
from typing import Dict, Tuple

from neo4j import Driver
from settings import settings
from utils.logging_config import setup_logging

logger = setup_logging(__name__)

# In-memory fallback rate limiter
_fallback_counts: Dict[Tuple[str, str], int] = {}
_fallback_date: str = ""
_fallback_lock = threading.Lock()


def check_rate_limit(driver: Driver, user_id: str, max_queries: int | None = None) -> bool:
    global _fallback_date
    if max_queries is None:
        max_queries = settings.RATE_LIMIT_MAX
    today = date.today().isoformat()
    
    # Reset fallback counts if date changed
    if _fallback_date != today:
        _fallback_counts.clear()
        _fallback_date = today
    
    try:
        with driver.session() as session:
            # Note: We increment first, then check. This means the counter may overshoot
            # when the limit is reached. This is acceptable because:
            # 1. The decrement-on-error fix needs the increment to happen before the check
            # 2. The overshoot is minimal (at most 1 request worth)
            result = session.run(
                """
                MERGE (r:RateLimit {user_id: $user_id, date: $date})
                SET r.count = coalesce(r.count, 0) + 1
                RETURN r.count AS count
                """,
                user_id=user_id,
                date=today,
            )
            count = result.single()["count"]
            return count <= max_queries
    except Exception as e:
        logger.warning(
            "Rate limit check failed, using in-memory fallback",
            extra={"user_id": user_id, "error": str(e)},
        )
        # In-memory fallback with thread safety
        key = (user_id, today)
        with _fallback_lock:
            _fallback_counts[key] = _fallback_counts.get(key, 0) + 1
            count = _fallback_counts[key]
        return count <= max_queries


def decrement_rate_limit(driver: Driver, user_id: str) -> None:
    """Decrement the rate limit counter (used when a request fails)."""
    today = date.today().isoformat()
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (r:RateLimit {user_id: $user_id, date: $date})
                SET r.count = CASE
                    WHEN r.count IS NULL OR r.count <= 0 THEN 0
                    ELSE r.count - 1
                END
                """,
                user_id=user_id,
                date=today,
            )
    except Exception as e:
        logger.warning(
            "Rate limit decrement failed",
            extra={"user_id": user_id, "error": str(e)},
        )
        # In-memory fallback
        key = (user_id, today)
        with _fallback_lock:
            current = _fallback_counts.get(key, 0)
            _fallback_counts[key] = max(0, current - 1)
