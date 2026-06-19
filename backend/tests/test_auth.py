from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from middleware.auth import get_current_user, AuthError

app = FastAPI()


@app.get("/test")
async def _endpoint(user: dict = Depends(get_current_user)):
    return {"user": user}


client = TestClient(app)


def test_missing_auth_header_returns_401():
    response = client.get("/test")
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


def test_invalid_token_format_returns_401():
    response = client.get("/test", headers={"Authorization": "NotBearer token"})
    assert response.status_code == 401


def test_expired_token_returns_401():
    with patch("middleware.auth.decode_jwt") as mock_decode:
        mock_decode.side_effect = AuthError("Token has expired")
        response = client.get(
            "/test", headers={"Authorization": "Bearer expired.jwt.token"}
        )
    assert response.status_code == 401


def test_valid_token_with_mocked_jwks():
    payload = {"sub": "auth0|user123", "permissions": ["read:repos"]}
    with patch("middleware.auth.decode_jwt") as mock_decode:
        mock_decode.return_value = payload
        response = client.get(
            "/test", headers={"Authorization": "Bearer valid.jwt.token"}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["sub"] == "auth0|user123"


def test_auth_error_exception():
    err = AuthError("test error")
    assert err.status_code == 401
    assert err.detail == "test error"


def test_jwks_network_error_returns_401():
    from jwt import PyJWKClientError
    with patch("middleware.auth.settings") as mock_settings:
        mock_settings.AUTH_ENABLED = True
        mock_settings.AUTH0_DOMAIN = "test.auth0.com"
        mock_settings.AUTH0_AUDIENCE = "https://api.test.com"
        with patch("middleware.auth.PyJWKClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("Connection refused")
            from middleware.auth import decode_jwt
            with pytest.raises(AuthError) as excinfo:
                decode_jwt("some.token.here")
            assert excinfo.value.status_code == 401


def test_jwks_timeout_error_returns_401():
    from jwt import PyJWKClientError
    with patch("middleware.auth.settings") as mock_settings:
        mock_settings.AUTH_ENABLED = True
        mock_settings.AUTH0_DOMAIN = "test.auth0.com"
        mock_settings.AUTH0_AUDIENCE = "https://api.test.com"
        with patch("middleware.auth.PyJWKClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get_signing_key_from_jwt.side_effect = PyJWKClientError("Timeout")
            from middleware.auth import decode_jwt
            with pytest.raises(AuthError) as excinfo:
                decode_jwt("some.token.here")
            assert excinfo.value.status_code == 401
