# Webhook Security Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical security vulnerability where webhook endpoint allows unauthenticated access when WEBHOOK_SECRET is not configured.

**Architecture:** Modify the webhook endpoint in `src/main.py` to return 503 Service Unavailable when WEBHOOK_SECRET is not configured in production, while allowing development mode with explicit bypass via environment variable.

**Tech Stack:** Python, FastAPI, pytest

---

### Task 1: Implement webhook authentication fix

**Files:**
- Modify: `src/main.py:79-96`
- Test: `tests/test_webhook_auth.py` (new file)

- [ ] **Step 1: Write failing test for production behavior**

```python
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

def test_webhook_refuses_when_secret_not_configured_in_production():
    """When WEBHOOK_SECRET is not set and ENV=production, return 503."""
    from src.main import app
    
    client = TestClient(app)
    
    # Mock settings to have no WEBHOOK_SECRET
    with patch('src.main.settings') as mock_settings:
        mock_settings.WEBHOOK_SECRET = ""
        mock_settings.WEBHOOK_SESSION_ID = ""
        
        # Set ENV to production
        with patch.dict(os.environ, {"ENV": "production"}):
            response = client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "push"},
                content=b"test"
            )
            assert response.status_code == 503
            assert response.json()["detail"] == "Webhook authentication not configured"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_webhook_auth.py::test_webhook_refuses_when_secret_not_configured_in_production -v`
Expected: FAIL with "status code 200 not 503" or similar

- [ ] **Step 3: Implement the fix in src/main.py**

Add `import os` at the top of the file, then modify the webhook endpoint logic:

```python
# In the webhook endpoint (lines 79-96):
if not settings.WEBHOOK_SECRET:
    env = os.getenv("ENV", "development").lower()
    if env == "production":
        logger.critical("WEBHOOK_SECRET not configured in production - refusing webhook")
        return JSONResponse(status_code=503, content={"detail": "Webhook authentication not configured"})
    elif os.getenv("WEBHOOK_AUTH_DISABLED", "false").lower() != "true":
        logger.warning("WEBHOOK_SECRET not configured - webhook authentication disabled")
        return JSONResponse(status_code=503, content={"detail": "Webhook authentication not configured"})
    else:
        logger.warning("WEBHOOK_SECRET not configured - authentication explicitly disabled via WEBHOOK_AUTH_DISABLED")
else:
    # existing signature verification code
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_webhook_auth.py::test_webhook_refuses_when_secret_not_configured_in_production -v`
Expected: PASS

- [ ] **Step 5: Add test for development mode with bypass**

```python
def test_webhook_allows_when_auth_disabled_in_development():
    """When WEBHOOK_SECRET is not set, ENV=development, and WEBHOOK_AUTH_DISABLED=true, allow."""
    from src.main import app
    
    client = TestClient(app)
    
    with patch('src.main.settings') as mock_settings:
        mock_settings.WEBHOOK_SECRET = ""
        mock_settings.WEBHOOK_SESSION_ID = ""
        
        # Set ENV to development and WEBHOOK_AUTH_DISABLED=true
        with patch.dict(os.environ, {"ENV": "development", "WEBHOOK_AUTH_DISABLED": "true"}):
            response = client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "push"},
                content=b"test"
            )
            # Should not be 503; likely 200 or 400 (invalid JSON)
            assert response.status_code != 503
```

- [ ] **Step 6: Run all webhook tests**

Run: `pytest tests/test_webhook_auth.py -v`
Expected: All tests pass

- [ ] **Step 7: Run linter**

Run: `ruff check src/main.py`
Expected: No errors

- [ ] **Step 8: Commit changes**

```bash
git add src/main.py tests/test_webhook_auth.py
git commit -m "fix: refuse webhook when secret not configured in production"
```

## Self-Review

**1. Spec coverage:** The fix implements all requirements:
- Returns 503 when WEBHOOK_SECRET not configured in production
- Allows development mode with explicit bypass via WEBHOOK_AUTH_DISABLED
- Logs appropriate warnings/critical messages

**2. Placeholder scan:** No placeholders found.

**3. Type consistency:** N/A for this simple change.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-08-webhook-security-fix.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**