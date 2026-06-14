from __future__ import annotations

import os
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientError

from utils.logging_config import setup_logging
from settings import settings

logger = setup_logging(__name__)

security = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def decode_jwt(token: str) -> dict[str, Any]:
    env = os.getenv("ENV", "development").lower()
    if not settings.AUTH_ENABLED:
        if env == "production":
            logger.critical(
                "AUTH_ENABLED is False in production — this is a security risk"
            )
            raise AuthError("Authentication is disabled in production")
        logger.debug("AUTH_ENABLED is False — skipping JWT validation")
        return {"sub": "anonymous", "permissions": []}

    domain = settings.AUTH0_DOMAIN or ""
    audience = settings.AUTH0_AUDIENCE or ""
    if not domain or not audience:
        logger.error(
            "AUTH_ENABLED is True but AUTH0_DOMAIN or AUTH0_AUDIENCE not set"
        )
        raise AuthError("Auth0 is not configured")

    jwks_url = f"https://{domain}/.well-known/jwks.json"
    jwks_client = PyJWKClient(jwks_url, cache_keys=True)

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{domain}/",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except PyJWKClientError:
        raise AuthError("Auth0 is unavailable — token validation failed")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    if credentials is None:
        raise AuthError()
    token = credentials.credentials
    return decode_jwt(token)
