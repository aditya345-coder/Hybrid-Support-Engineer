"""Tests for rate_limit.py — Redis-backed rate limiting with in-memory fallback."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_redis_store():
    """Create a mock RedisStore for rate_limit tests."""
    mock = MagicMock()
    mock._check_available.return_value = True
    mock.check_rate_limit_sync.return_value = True
    mock.decrement_rate_limit_sync.return_value = None
    mock.check_rate_limit_namespace_sync.return_value = True
    return mock


@pytest.fixture(autouse=True)
def patch_redis_store(mock_redis_store):
    """Patch the redis_store singleton in rate_limit module."""
    with patch("middleware.rate_limit.redis_store", mock_redis_store):
        yield


@pytest.fixture(autouse=True)
def _reset_fallback_state():
    """Reset in-memory fallback state between tests."""
    import middleware.rate_limit as rl
    rl._fallback_counts.clear()
    rl._fallback_date = ""
    yield
    rl._fallback_counts.clear()
    rl._fallback_date = ""


def test_allows_when_under_limit(mock_redis_store):
    mock_redis_store.check_rate_limit_sync.return_value = True
    from middleware.rate_limit import check_rate_limit

    result = check_rate_limit("user-1", max_queries=50)
    assert result is True
    mock_redis_store.check_rate_limit_sync.assert_called_once_with("user-1", 50)


def test_blocks_when_over_limit(mock_redis_store):
    mock_redis_store.check_rate_limit_sync.return_value = False
    from middleware.rate_limit import check_rate_limit

    result = check_rate_limit("user-1", max_queries=50)
    assert result is False


def test_allows_at_exact_limit(mock_redis_store):
    mock_redis_store.check_rate_limit_sync.return_value = True
    from middleware.rate_limit import check_rate_limit

    result = check_rate_limit("user-1", max_queries=50)
    assert result is True


def test_uses_settings_default_when_max_queries_none(mock_redis_store, monkeypatch):
    from settings import settings
    monkeypatch.setattr(settings, "RATE_LIMIT_MAX", 10)
    mock_redis_store.check_rate_limit_sync.return_value = True
    from middleware.rate_limit import check_rate_limit

    result = check_rate_limit("user-1")
    mock_redis_store.check_rate_limit_sync.assert_called_once_with("user-1", 10)


def test_delegates_to_redis_decrement(mock_redis_store):
    from middleware.rate_limit import decrement_rate_limit

    decrement_rate_limit("user-1")
    mock_redis_store.decrement_rate_limit_sync.assert_called_once_with("user-1")


def test_namespace_check_delegates_to_redis(mock_redis_store):
    mock_redis_store.check_rate_limit_namespace_sync.return_value = True
    from middleware.rate_limit import check_rate_limit_namespace

    result = check_rate_limit_namespace("user-1", "cleanup", 5)
    assert result is True
    mock_redis_store.check_rate_limit_namespace_sync.assert_called_once_with("user-1", "cleanup", 5)


def test_falls_back_to_in_memory_when_redis_unavailable(mock_redis_store):
    """When Redis is unavailable, fall back to in-memory counter."""
    mock_redis_store._check_available.return_value = False
    from middleware.rate_limit import check_rate_limit

    result = check_rate_limit("user-1", max_queries=50)
    # In-memory fallback starts at 1, under limit of 50
    assert result is True
    mock_redis_store.check_rate_limit_sync.assert_not_called()


def test_falls_back_to_in_memory_on_redis_error(mock_redis_store):
    """When Redis throws an error, fall back to in-memory counter."""
    mock_redis_store.check_rate_limit_sync.side_effect = Exception("Connection lost")
    from middleware.rate_limit import check_rate_limit

    result = check_rate_limit("user-1", max_queries=50)
    # In-memory fallback starts at 1, under limit of 50
    assert result is True


def test_decrement_falls_back_to_in_memory_when_redis_unavailable(mock_redis_store):
    """When Redis is unavailable, decrement uses in-memory fallback."""
    mock_redis_store._check_available.return_value = False
    from middleware.rate_limit import decrement_rate_limit

    # Should not raise
    decrement_rate_limit("user-1")
    mock_redis_store.decrement_rate_limit_sync.assert_not_called()


def test_namespace_falls_back_to_in_memory_when_redis_unavailable(mock_redis_store):
    """When Redis is unavailable, namespace check uses in-memory fallback."""
    mock_redis_store._check_available.return_value = False
    from middleware.rate_limit import check_rate_limit_namespace

    result = check_rate_limit_namespace("user-1", "cleanup", 5)
    # In-memory fallback starts at 1, under limit of 5
    assert result is True


def test_in_memory_fallback_increments_correctly(mock_redis_store):
    """Verify in-memory fallback counter increments across calls."""
    mock_redis_store._check_available.return_value = False
    from middleware.rate_limit import check_rate_limit

    # First call: count=1, under limit 2
    assert check_rate_limit("user-1", max_queries=2) is True
    # Second call: count=2, at limit 2
    assert check_rate_limit("user-1", max_queries=2) is True
    # Third call: count=3, over limit 2
    assert check_rate_limit("user-1", max_queries=2) is False
