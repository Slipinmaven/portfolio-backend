from __future__ import annotations

import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import NoReturn
from uuid import UUID

from jwt import InvalidTokenError

from app.application.auth.dto import AuthTokens, LoginData
from app.application.errors import AuthenticationError, ResourceNotFoundError
from app.core.config import settings
from app.core.logging import get_security_logger
from app.infrastructure.database.models.session import Session
from app.infrastructure.database.models.trusted_device import TrustedDevice
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.authentication import AuthenticationUnitOfWork
from app.infrastructure.security.device_metadata import parse_device_metadata
from app.infrastructure.security.passwords import verify_password
from app.infrastructure.security.tokens import (
    create_access_token,
    decode_access_token,
    hash_token,
    new_opaque_token,
)

security_logger = get_security_logger()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _client_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


class AuthService:
    def __init__(self, unit_of_work: AuthenticationUnitOfWork) -> None:
        self.uow = unit_of_work

    async def login(self, data: LoginData) -> AuthTokens:
        now = datetime.now(timezone.utc)
        ip_address = _client_ip(data.client_ip)
        normalized_email = normalize_email(data.email)
        client_key = hash_token(f"{ip_address or 'unknown'}\0{normalized_email}")
        if await self.uow.login_attempts.is_blocked(client_key, now=now):
            security_logger.warning(
                "Login attempt rate limited",
                extra={
                    "event": "auth.login_rate_limited",
                    "ip_address": ip_address,
                },
            )
            raise AuthenticationError("Invalid email or password")

        user = await self.uow.users.get_by_email(
            email=normalized_email
        )
        if user is None or not user.is_active:
            await self._record_failed_login(data, client_key, now)

        if not await verify_password(data.password, user.password_hash):
            await self._record_failed_login(data, client_key, now)

        device: TrustedDevice | None = None
        device_token: str | None = None
        device_max_age: int | None = None

        if data.trusted_device:
            device, device_token, device_max_age = await self._authorize_device(
                user_id=user.id,
                token=data.trusted_device_token,
                ip_address=ip_address,
                user_agent=data.user_agent,
                now=now,
            )

        refresh_token = new_opaque_token()
        login_session = Session(
            user_id=user.id,
            trusted_device_id=device.id if device is not None else None,
            refresh_token_hash=hash_token(refresh_token),
            ip_address=ip_address,
            user_agent=(data.user_agent or "")[:255] or None,
            expires_at=now + timedelta(days=settings.refresh_session_days),
            last_activity_at=now,
        )
        await self.uow.sessions.create(login_session)

        user.last_login_at = now
        access_token, access_expires_in = create_access_token(
            user_id=user.id,
            session_id=login_session.id,
            now=now,
        )
        await self.uow.login_attempts.clear(client_key)
        await self.uow.commit()

        security_logger.info(
            "Login successful",
            extra={
                "event": "auth.login_succeeded",
                "user_id": user.id,
                "ip_address": ip_address,
            },
        )
        return AuthTokens(
            user_id=str(user.id),
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=access_expires_in,
            refresh_max_age=int((login_session.expires_at - now).total_seconds()),
            trusted_device_token=device_token,
            trusted_device_max_age=device_max_age,
        )

    async def refresh(self, refresh_token: str) -> AuthTokens:
        now = datetime.now(timezone.utc)
        session = await self.uow.sessions.get_by_refresh_token_hash(
            hash_token(refresh_token)
        )
        if session is None or session.revoked_at is not None:
            raise AuthenticationError("Refresh token is invalid or expired.")

        if session.expires_at <= now:
            raise AuthenticationError("Refresh token is invalid or expired.")

        if now - session.last_activity_at > timedelta(
            minutes=settings.session_idle_minutes
        ):
            await self._revoke_session(session, now, "idle_timeout")
            raise AuthenticationError("Session expired due to inactivity.")

        user = await self.uow.users.get_by_id(session.user_id)
        if user is None or not user.is_active:
            await self._revoke_session(session, now, "user_unavailable")
            raise AuthenticationError("Refresh token is invalid or expired.")

        if session.trusted_device_id is not None:
            device = await self.uow.trusted_devices.get_by_id(
                session.trusted_device_id
            )
            if (
                device is None
                or device.revoked_at is not None
                or device.expires_at <= now
            ):
                await self._revoke_session(session, now, "trusted_device_invalid")
                raise AuthenticationError("Refresh token is invalid or expired.")

        rotated_refresh_token = new_opaque_token()
        session.refresh_token_hash = hash_token(rotated_refresh_token)
        session.last_activity_at = now
        access_token, access_expires_in = create_access_token(
            user_id=user.id,
            session_id=session.id,
            now=now,
        )
        await self.uow.commit()
        return AuthTokens(
            user_id=str(user.id),
            access_token=access_token,
            refresh_token=rotated_refresh_token,
            access_expires_in=access_expires_in,
            refresh_max_age=max(int((session.expires_at - now).total_seconds()), 0),
        )

    async def authenticate_access_token(self, token: str) -> User:
        try:
            claims = decode_access_token(token)
            user_id = UUID(claims["sub"])
            session_id = UUID(claims["sid"])
        except (InvalidTokenError, KeyError, TypeError, ValueError):
            raise AuthenticationError("Access token is invalid or expired.") from None

        now = datetime.now(timezone.utc)
        session = await self.uow.sessions.get_by_id(session_id)
        if (
            session is None
            or session.user_id != user_id
            or session.revoked_at is not None
            or session.expires_at <= now
        ):
            raise AuthenticationError("Access token is invalid or expired.")

        if now - session.last_activity_at > timedelta(
            minutes=settings.session_idle_minutes
        ):
            await self._revoke_session(session, now, "idle_timeout")
            raise AuthenticationError("Session expired due to inactivity.")

        if session.trusted_device_id is not None:
            device = await self.uow.trusted_devices.get_by_id(
                session.trusted_device_id
            )
            if (
                device is None
                or device.revoked_at is not None
                or device.expires_at <= now
            ):
                await self._revoke_session(session, now, "trusted_device_invalid")
                raise AuthenticationError("Access token is invalid or expired.")

        user = await self.uow.users.get_by_id(user_id)
        if user is None or not user.is_active:
            await self._revoke_session(session, now, "user_unavailable")
            raise AuthenticationError("Access token is invalid or expired.")

        if (
            now - session.last_activity_at
        ).total_seconds() >= settings.session_activity_update_seconds:
            session.last_activity_at = now
            await self.uow.commit()
        return user

    async def list_sessions(self, user_id: UUID) -> list[Session]:
        return await self.uow.sessions.get_by_user_id(user_id)

    async def revoke_session(
        self,
        user_id: UUID,
        session_id: UUID,
        *,
        presented_refresh_token: str | None = None,
    ) -> bool:
        session = await self.uow.sessions.get_by_id(session_id)
        if session is None or session.user_id != user_id:
            raise ResourceNotFoundError("Session not found.")
        refresh_matches = (
            presented_refresh_token is not None
            and secrets.compare_digest(
                session.refresh_token_hash,
                hash_token(presented_refresh_token),
            )
        )
        if session.revoked_at is None:
            now = datetime.now(timezone.utc)
            session.revoked_at = now
            session.revocation_reason = "user_revoked"
            await self.uow.commit()
        return refresh_matches

    async def logout(self, refresh_token: str | None) -> None:
        if refresh_token is None:
            return
        session = await self.uow.sessions.get_by_refresh_token_hash(
            hash_token(refresh_token)
        )
        if session is not None and session.revoked_at is None:
            await self._revoke_session(
                session,
                datetime.now(timezone.utc),
                "logout",
            )

    async def list_trusted_devices(self, user_id: UUID) -> list[TrustedDevice]:
        return await self.uow.trusted_devices.get_by_user_id(user_id)

    async def revoke_trusted_device(
        self,
        user_id: UUID,
        device_id: UUID,
        *,
        presented_token: str | None,
    ) -> bool:
        device = await self.uow.trusted_devices.get_by_id(device_id)
        if device is None or device.user_id != user_id:
            raise ResourceNotFoundError("Trusted device not found.")

        now = datetime.now(timezone.utc)
        token_matches = (
            presented_token is not None
            and secrets.compare_digest(
                device.device_token_hash,
                hash_token(presented_token),
            )
        )
        if device.revoked_at is None:
            device.revoked_at = now
            device.revocation_reason = "user_revoked"
            await self.uow.sessions.revoke_active_for_device(
                device.id,
                revoked_at=now,
                reason="trusted_device_revoked",
            )
            await self.uow.commit()
        return token_matches

    async def _record_failed_login(
        self,
        data: LoginData,
        client_key: str,
        now: datetime,
    ) -> NoReturn:
        await self.uow.login_attempts.record_failure(
            client_key,
            now=now,
            window=timedelta(minutes=settings.login_failure_window_minutes),
            maximum_failures=settings.login_failure_limit,
        )
        await self.uow.commit()
        self._raise_authentication_error(data)

    async def _authorize_device(
        self,
        *,
        user_id: UUID,
        token: str | None,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> tuple[TrustedDevice, str, int]:
        (
            device_name,
            device_type,
            browser,
            operating_system,
        ) = parse_device_metadata(user_agent)
        device = None
        if token:
            candidate = await self.uow.trusted_devices.get_by_device_token_hash(
                hash_token(token)
            )
            if (
                candidate is not None
                and candidate.user_id == user_id
                and candidate.revoked_at is None
                and candidate.expires_at > now
            ):
                device = candidate

        new_token = new_opaque_token()
        if device is None:
            expires_at = now + timedelta(days=settings.trusted_device_days)
            device = TrustedDevice(
                user_id=user_id,
                device_token_hash=hash_token(new_token),
                ip_address=ip_address,
                device_name=device_name,
                device_type=device_type,
                browser=browser,
                operating_system=operating_system,
                expires_at=expires_at,
            )
            await self.uow.trusted_devices.create(device)
        else:
            device.device_token_hash = hash_token(new_token)
            device.ip_address = ip_address
            device.device_name = device_name
            device.device_type = device_type
            device.browser = browser
            device.operating_system = operating_system
            device.last_used_at = now

        max_age = max(int((device.expires_at - now).total_seconds()), 0)
        return device, new_token, max_age

    async def _revoke_session(
        self,
        session: Session,
        now: datetime,
        reason: str,
    ) -> None:
        session.revoked_at = now
        session.revocation_reason = reason
        await self.uow.commit()

    @staticmethod
    def _raise_authentication_error(data: LoginData) -> NoReturn:
        security_logger.warning(
            "Login attempt failed",
            extra={
                "event": "auth.login_failed",
                "ip_address": _client_ip(data.client_ip),
            },
        )
        raise AuthenticationError("Invalid email or password")
