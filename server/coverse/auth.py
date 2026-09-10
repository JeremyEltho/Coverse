"""Authentication.

Two real modes and one development mode:

* **HS256** -- the classic Supabase JWT secret. Verified locally, no network.
* **JWKS**  -- Supabase's asymmetric signing keys, fetched from the project's
  `.well-known` endpoint and cached.
* **dev**   -- when no Supabase settings are present the token is trusted as an
  opaque user id, so the stack runs with nothing configured. `auth_required`
  must stay false for this, and it is refused outright if a project URL is set.

Websockets carry the token in the query string, because browsers cannot set
headers on a WebSocket handshake.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient

from .config import Settings, get_settings

# WebSocket close codes. 4401/4403 mirror HTTP 401/403 in the application range.
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403


@dataclass(frozen=True)
class User:
    id: str
    email: str = ""
    name: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0] or self.id[:8]


class AuthError(Exception):
    pass


_jwk_client: PyJWKClient | None = None
_jwk_client_url: str = ""


def _get_jwk_client(settings: Settings) -> PyJWKClient:
    global _jwk_client, _jwk_client_url
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if _jwk_client is None or _jwk_client_url != url:
        # PyJWKClient caches keys and refetches on unknown kid.
        _jwk_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwk_client_url = url
    return _jwk_client


def _user_from_claims(claims: dict[str, Any]) -> User:
    metadata = claims.get("user_metadata") or {}
    return User(
        id=str(claims.get("sub") or ""),
        email=str(claims.get("email") or ""),
        name=str(metadata.get("full_name") or metadata.get("name") or ""),
    )


def verify_token(token: str, settings: Settings | None = None) -> User:
    """Verify a token and return the user, or raise `AuthError`."""
    settings = settings or get_settings()
    token = (token or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise AuthError("missing token")

    if settings.supabase_jwt_secret:
        try:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {exc}") from exc
        return _user_from_claims(claims)

    if settings.supabase_url:
        try:
            signing_key = _get_jwk_client(settings).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                options={"verify_aud": False},
            )
        except (jwt.PyJWTError, httpx.HTTPError) as exc:
            raise AuthError(f"invalid token: {exc}") from exc
        return _user_from_claims(claims)

    # Development mode: no verification is possible, so make the trust explicit.
    if settings.auth_required:
        raise AuthError("auth is required but no Supabase credentials are configured")
    return User(id=token[:64], name=token[:64])


def anonymous_user() -> User:
    return User(id=f"anon-{int(time.time() * 1000) % 1_000_000}", name="Anonymous")


async def current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    """FastAPI dependency for HTTP routes."""
    token = request.headers.get("authorization", "")
    if not token:
        token = request.query_params.get("token", "")

    if not token:
        if settings.auth_required:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing authorization")
        return anonymous_user()

    try:
        return verify_token(token, settings)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


def user_from_ws_token(token: str, settings: Settings | None = None) -> User | None:
    """Resolve a websocket's `?token=` param. Returns None when unauthorized."""
    settings = settings or get_settings()
    if not token:
        return None if settings.auth_required else anonymous_user()
    try:
        return verify_token(token, settings)
    except AuthError:
        return None
