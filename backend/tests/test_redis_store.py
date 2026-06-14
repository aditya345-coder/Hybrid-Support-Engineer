"""Tests for RedisStore — session state, rate limiting, and connection management."""
import json
from datetime import date
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from database.redis_store import RedisStore


@pytest.fixture(autouse=True)
def _set_redis_url(monkeypatch):
    """Ensure REDIS_URL is set so sync methods don't bail out."""
    monkeypatch.setattr("database.redis_store.settings.REDIS_URL", "rediss://fake:token@localhost:6379")


@pytest.fixture
def mock_client():
    """Mock Redis client with sensible defaults for sync operations."""
    c = MagicMock()
    c.hset.return_value = 1
    c.hgetall.return_value = {}
    c.expire.return_value = True
    c.delete.return_value = 1
    c.eval.return_value = 1
    c.scan_iter.return_value = iter([])
    c.ping.return_value = True
    return c


@pytest.fixture
def mock_async_client():
    """Mock async Redis client."""
    c = AsyncMock()
    c.hset = AsyncMock(return_value=1)
    c.hgetall = AsyncMock(return_value={})
    c.expire = AsyncMock(return_value=True)
    c.delete = AsyncMock(return_value=1)
    c.eval = AsyncMock(return_value=1)
    c.ping = AsyncMock(return_value=True)
    return c


@pytest.fixture
def store(mock_client, mock_async_client):
    """Create a RedisStore with mocked clients."""
    s = RedisStore()
    s._client = mock_async_client
    s._sync_client = mock_client
    return s


# ── Session State Tests ────────────────────────────────────────────


class TestSaveAndGetSession:
    def test_save_session_sets_hash_and_ttl(self, store, mock_client):
        store.save_session_sync("sess1", {
            "repo_url": "https://github.com/test/repo",
            "stage": "running",
            "completed_phases": [],
        })
        mock_client.hset.assert_called_once()
        # key is passed as positional arg, mapping as keyword
        assert mock_client.hset.call_args[0][0] == "session:sess1"
        mock_client.expire.assert_called_once_with("session:sess1", 86400)

    def test_get_session_returns_none_when_missing(self, store, mock_client):
        mock_client.hgetall.return_value = {}
        result = store.get_session_sync("nonexistent")
        assert result is None

    def test_get_session_parses_completed_phases_json(self, store, mock_client):
        mock_client.hgetall.return_value = {
            "stage": "running",
            "completed_phases": '["cloning","parsing_docs"]',
            "percent": "45",
        }
        result = store.get_session_sync("sess1")
        assert result["completed_phases"] == ["cloning", "parsing_docs"]
        assert result["percent"] == "45"

    def test_save_session_serializes_list_to_json(self, store, mock_client):
        store.save_session_sync("sess1", {"completed_phases": ["a", "b"]})
        call_kwargs = mock_client.hset.call_args[1]
        mapping = call_kwargs["mapping"]
        assert mapping["completed_phases"] == json.dumps(["a", "b"])


class TestMarkPhaseComplete:
    def test_mark_phase_complete_calls_lua_script(self, store, mock_client):
        result = store.mark_phase_complete_sync("sess1", "cloning")
        mock_client.eval.assert_called_once()
        args = mock_client.eval.call_args[0]
        assert "KEYS[1]" in args[0]  # Lua script
        assert args[2] == "session:sess1"
        assert args[3] == "cloning"
        assert result is True

    def test_mark_phase_complete_returns_false_when_phase_exists(self, store, mock_client):
        mock_client.eval.return_value = 0
        result = store.mark_phase_complete_sync("sess1", "cloning")
        assert result is False


class TestDeleteSession:
    def test_delete_session_calls_redis_delete(self, store, mock_client):
        store.delete_session_sync("sess1")
        mock_client.delete.assert_called_once_with("session:sess1")


class TestGetRunningSessions:
    @pytest.mark.asyncio
    async def test_get_running_sessions_filters_by_stage(self, store, mock_async_client):
        def hgetall_side_effect(key):
            data = {
                "session:sess1": {"stage": "running", "repo_url": "url1"},
                "session:sess2": {"stage": "complete", "repo_url": "url2"},
                "session:sess3": {"stage": "running", "repo_url": "url3"},
            }
            return data.get(key, {})

        mock_async_client.scan_iter = AsyncMock()
        mock_async_client.scan_iter.return_value = AsyncMock()()
        # Build an async iterator for scan_iter
        async def fake_scan_iter(*args, **kwargs):
            for key in ["session:sess1", "session:sess2", "session:sess3"]:
                yield key
        mock_async_client.scan_iter = fake_scan_iter
        mock_async_client.hgetall = AsyncMock(side_effect=hgetall_side_effect)

        result = await store.get_running_sessions()
        assert len(result) == 2
        assert result[0]["session_id"] == "sess1"
        assert result[1]["session_id"] == "sess3"


# ── Rate Limiting Tests ────────────────────────────────────────────


class TestRateLimit:
    def test_check_rate_limit_increments_and_checks(self, store, mock_client):
        mock_client.eval.return_value = 5
        result = store.check_rate_limit_sync("user1", 10)
        assert result is True
        mock_client.eval.assert_called_once()

    def test_check_rate_limit_blocks_at_limit(self, store, mock_client):
        mock_client.eval.return_value = 11
        result = store.check_rate_limit_sync("user1", 10)
        assert result is False

    def test_check_rate_limit_allows_at_exact_limit(self, store, mock_client):
        mock_client.eval.return_value = 10
        result = store.check_rate_limit_sync("user1", 10)
        assert result is True

    def test_decrement_rate_limit_calls_lua_script(self, store, mock_client):
        store.decrement_rate_limit_sync("user1")
        mock_client.eval.assert_called_once()
        args = mock_client.eval.call_args[0]
        assert "DECR" in args[0]  # Lua script contains DECR

    def test_check_rate_limit_namespace_independent_buckets(self, store, mock_client):
        mock_client.eval.return_value = 1
        result1 = store.check_rate_limit_namespace_sync("user1", "cleanup", 5)
        result2 = store.check_rate_limit_namespace_sync("user1", "cleanup", 5)
        assert result1 is True
        assert result2 is True
        assert mock_client.eval.call_count == 2


class TestRateLimitKeyGeneration:
    def test_rate_limit_key_without_namespace(self, store):
        key = store._rate_limit_key("user1")
        today = date.today().isoformat()
        assert key == f"ratelimit:user1:{today}"

    def test_rate_limit_key_with_namespace(self, store):
        key = store._rate_limit_key("user1", "cleanup")
        today = date.today().isoformat()
        assert key == f"ratelimit:user1:{today}:cleanup"


# ── Connection Health Tests ────────────────────────────────────────


class TestConnectionHealth:
    @pytest.mark.asyncio
    async def test_ping_returns_true_when_connected(self, store, mock_async_client):
        result = await store.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_returns_false_on_error(self, store, mock_async_client):
        mock_async_client.ping = AsyncMock(side_effect=Exception("Connection refused"))
        result = await store.ping()
        assert result is False


# ── Fallback Tests ─────────────────────────────────────────────────


class TestFallbackBehavior:
    def test_save_session_no_error_when_redis_unavailable(self, mock_client):
        """Verify save_session_sync doesn't crash when Redis is unavailable."""
        s = RedisStore()
        s._sync_client = mock_client
        mock_client.hset.side_effect = Exception("Connection lost")
        # Should not raise
        s.save_session_sync("sess1", {"stage": "running"})

    def test_get_session_returns_none_when_redis_unavailable(self, mock_client):
        """Verify get_session_sync returns None when Redis is unavailable."""
        s = RedisStore()
        s._sync_client = mock_client
        mock_client.hgetall.side_effect = Exception("Connection lost")
        result = s.get_session_sync("sess1")
        assert result is None
