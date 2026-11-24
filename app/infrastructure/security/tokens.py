from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt

from app.core.config import settings


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _signing_key() -> str:
    key = settings.jwt_secret_key.get_secret_value()
    if len(key.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 bytes before issuing tokens."
        )
    return key


def create_access_token(
    user_id: UUID,
    session_id: UUID,
    *,
    now: datetime | None = None,
) -> tuple[str, int]:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_minutes)
    lifetime = int((expires_at - issued_at).total_seconds())
    encoded = jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": issued_at,
            "exp": expires_at,
            "jti": str(uuid4()),
        },
        _signing_key(),
        algorithm="HS256",
    )
    return encoded, lifetime


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        _signing_key(),
        algorithms=["HS256"],
        options={"require": ["sub", "sid", "iat", "exp", "jti"]},
    )

