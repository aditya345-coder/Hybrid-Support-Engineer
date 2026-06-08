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
