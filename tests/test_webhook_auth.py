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


def test_webhook_refuses_when_auth_disabled_not_true():
    """When WEBHOOK_SECRET is not set, ENV=development, and WEBHOOK_AUTH_DISABLED not 'true', return 503."""
    from src.main import app

    client = TestClient(app)

    with patch('src.main.settings') as mock_settings:
        mock_settings.WEBHOOK_SECRET = ""
        mock_settings.WEBHOOK_SESSION_ID = ""

        # Set ENV to development and WEBHOOK_AUTH_DISABLED= false (or absent)
        with patch.dict(os.environ, {"ENV": "development", "WEBHOOK_AUTH_DISABLED": "false"}):
            response = client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "push"},
                content=b"test"
            )
            assert response.status_code == 503
            assert response.json()["detail"] == "Webhook authentication not configured"


def test_webhook_with_secret_proceeds_to_signature_verification():
    """When WEBHOOK_SECRET is set, should proceed to signature verification."""
    from src.main import app

    client = TestClient(app)

    with patch('src.main.settings') as mock_settings:
        mock_settings.WEBHOOK_SECRET = "test_secret"
        mock_settings.WEBHOOK_SESSION_ID = ""

        # Send request without signature header; should fail with 403
        response = client.post(
            "/webhook/github",
            headers={"X-GitHub-Event": "push"},
            content=b"test"
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Missing signature"