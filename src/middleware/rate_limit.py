import threading
from datetime import date
from typing import Dict, Tuple

from database.redis_store import get_redis_store
from settings import settings
from utils.logging_config import setup_logging

logger = setup_logging(__name__)

# In-memory fallback rate limiter (when Redis unavailable)
_fallback_counts: Dict[Tuple[str, str], int] = {}
_fallback_date: str = ""
_fallback_lock = threading.Lock()

redis_store = get_redis_store()  # shared singleton — same instance as main.py


def check_rate_limit(user_id: str, max_queries: int | None = None) -> bool:
    if max_queries is None:
        max_queries = settings.RATE_LIMIT_MAX

    # Try Redis first
    if redis_store._check_available():
        try:
            return redis_store.check_rate_limit_sync(user_id, max_queries)
        except Exception as e:
            logger.warning(
                "Redis rate limit check failed, using in-memory fallback",
                extra={"user_id": user_id, "error": str(e)},
            )

    # In-memory fallback
    today = date.today().isoformat()
    global _fallback_date
    if _fallback_date != today:
        _fallback_counts.clear()
        _fallback_date = today

    key = (user_id, today)
    with _fallback_lock:
        _fallback_counts[key] = _fallback_counts.get(key, 0) + 1
        count = _fallback_counts[key]
    return count <= max_queries


def decrement_rate_limit(user_id: str) -> None:
    """Decrement the rate limit counter (used when a request fails)."""
    if redis_store._check_available():
        try:
            redis_store.decrement_rate_limit_sync(user_id)
            return
        except Exception as e:
            logger.warning(
                "Redis rate limit decrement failed, using in-memory fallback",
                extra={"user_id": user_id, "error": str(e)},
            )

    # In-memory fallback
    today = date.today().isoformat()
    key = (user_id, today)
    with _fallback_lock:
        current = _fallback_counts.get(key, 0)
        _fallback_counts[key] = max(0, current - 1)


def check_rate_limit_namespace(user_id: str, namespace: str, max_queries: int) -> bool:
    """Check rate limit using a specific namespace (e.g., 'cleanup:{user_id}')."""
    if redis_store._check_available():
        try:
            return redis_store.check_rate_limit_namespace_sync(user_id, namespace, max_queries)
        except Exception as e:
            logger.warning(
                "Redis rate limit check failed, using in-memory fallback",
                extra={"user_id": user_id, "namespace": namespace, "error": str(e)},
            )

    # In-memory fallback
    today = date.today().isoformat()
    cache_key = (f"{namespace}:{user_id}", today)
    with _fallback_lock:
        _fallback_counts[cache_key] = _fallback_counts.get(cache_key, 0) + 1
        count = _fallback_counts[cache_key]
    return count <= max_queries
