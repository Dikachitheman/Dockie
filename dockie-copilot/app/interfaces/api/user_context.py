from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class RequestUserContext:
    user_id: str
    user_email: str | None = None


@lru_cache(maxsize=1)
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Cached JWKS client — fetches and caches the public keys from Supabase."""
    return PyJWKClient(jwks_url, cache_keys=True)


def _extract_user_from_jwt(token: str) -> tuple[str, str | None] | None:
    """Verify a Supabase JWT (ES256 via JWKS) and return (user_id, email).
    Returns None if no JWKS URL is configured (dev mode).
    Raises HTTP 401 for expired or invalid tokens when verification is enabled."""
    settings = get_settings()

    if not settings.supabase_jwks_url:
        return None

    try:
        client = _get_jwks_client(settings.supabase_jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
        user_id: str = payload.get("sub", "")
        email: str | None = payload.get("email")
        if not user_id:
            return None
        return user_id, email
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except jwt.InvalidTokenError as exc:
        logger.warning("jwt_verification_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")
    except Exception as exc:
        logger.warning("jwks_verification_error", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not verify token.")


async def get_request_user_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> RequestUserContext:
    settings = get_settings()

    # Verify JWT via JWKS when SUPABASE_JWKS_URL is configured
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        result = _extract_user_from_jwt(token)
        if result is not None:
            user_id, email = result
            return RequestUserContext(user_id=user_id, user_email=email)

    # Dev fallback: trust X-User-ID header (no JWKS URL configured)
    user_id = x_user_id or x_session_id or settings.adk_user_id
    return RequestUserContext(user_id=user_id, user_email=x_user_email)
