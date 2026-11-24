import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.application.auth.dto import LoginData
from app.application.auth.service import AuthService
from app.application.errors import AuthenticationError, ResourceNotFoundError
from app.infrastructure.database.models.session import Session
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.authentication import AuthenticationUnitOfWork
from app.infrastructure.security.tokens import create_access_token, hash_token


class AuthSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.user = MagicMock(spec=User)
        self.user.id = self.user_id
        self.user.is_active = True
        self.user.password_hash = "unused-in-these-tests"
        self.user.email = "user@example.com"
        self.user.role = "editor"

        self.uow = MagicMock(spec=AuthenticationUnitOfWork)
        self.uow.users = MagicMock()
        self.uow.sessions = MagicMock()
        self.uow.trusted_devices = MagicMock()
        self.uow.users.get_by_email = AsyncMock(return_value=self.user)
        self.uow.users.get_by_id = AsyncMock(return_value=self.user)
        self.uow.sessions.get_by_refresh_token_hash = AsyncMock()
        self.uow.sessions.get_by_id = AsyncMock()
        self.uow.sessions.get_by_user_id = AsyncMock(return_value=[])
        self.uow.sessions.create = AsyncMock(side_effect=self._persist_with_id)
        self.uow.sessions.revoke_active_for_device = AsyncMock()
        self.uow.trusted_devices.get_by_device_token_hash = AsyncMock(
            return_value=None
        )
        self.uow.trusted_devices.get_by_id = AsyncMock()
        self.uow.trusted_devices.get_by_user_id = AsyncMock(return_value=[])
        self.uow.trusted_devices.revoke_active_for_user = AsyncMock()
        self.uow.trusted_devices.create = AsyncMock(side_effect=self._persist_with_id)
        self.uow.login_attempts = MagicMock()
        self.uow.login_attempts.is_blocked = AsyncMock(return_value=False)
        self.uow.login_attempts.record_failure = AsyncMock()
        self.uow.login_attempts.clear = AsyncMock()
        self.uow.commit = AsyncMock()
        self.service = AuthService(self.uow)

    @staticmethod
    async def _persist_with_id(entity):
        if entity.id is None:
            entity.id = uuid4()
        return entity

    @patch("app.infrastructure.security.tokens._signing_key", return_value="s" * 48)
    @patch("app.application.auth.service.verify_password", new_callable=AsyncMock)
    async def test_login_without_trust_creates_unlinked_session(
        self, verify_password, _signing_key
    ) -> None:
        verify_password.return_value = True

        tokens = await self.service.login(
            LoginData(
                email="user@example.com",
                password="correct",
                client_ip="203.0.113.8",
                user_agent="Test Agent",
            )
        )

        login_session = self.uow.sessions.create.await_args.args[0]
        self.assertIsNone(login_session.trusted_device_id)
        self.assertEqual(login_session.ip_address, "203.0.113.8")
        self.assertEqual(login_session.user_agent, "Test Agent")
        self.assertNotEqual(login_session.refresh_token_hash, tokens.refresh_token)
        self.assertEqual(tokens.refresh_max_age, 7 * 24 * 60 * 60)
        self.assertIsNone(tokens.trusted_device_token)
        self.uow.login_attempts.clear.assert_awaited_once()
        self.uow.trusted_devices.create.assert_not_awaited()
        self.uow.commit.assert_awaited_once()

    @patch("app.infrastructure.security.tokens._signing_key", return_value="s" * 48)
    @patch("app.application.auth.service.verify_password", new_callable=AsyncMock)
    async def test_login_registers_requested_trusted_device_and_links_session(
        self, verify_password, _signing_key
    ) -> None:
        verify_password.return_value = True

        tokens = await self.service.login(
            LoginData(
                email="user@example.com",
                password="correct",
                trusted_device=True,
                client_ip="203.0.113.8",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
        )

        device = self.uow.trusted_devices.create.await_args.args[0]
        login_session = self.uow.sessions.create.await_args.args[0]
        self.assertEqual(login_session.trusted_device_id, device.id)
        self.assertEqual(device.user_id, self.user_id)
        self.assertEqual(device.device_name, "Windows device")
        self.assertEqual(device.device_type, "desktop")
        self.assertEqual(device.browser, "Chrome")
        self.assertEqual(device.operating_system, "Windows")
        device_token = tokens.trusted_device_token
        if device_token is None:
            self.fail("Login did not return a trusted-device token")
        self.assertEqual(device.device_token_hash, hash_token(device_token))
        self.assertEqual(tokens.trusted_device_max_age, 30 * 24 * 60 * 60)
        self.uow.commit.assert_awaited_once()

    @patch("app.infrastructure.security.tokens._signing_key", return_value="s" * 48)
    async def test_refresh_rotates_token_without_extending_absolute_expiry(
        self, _signing_key
    ) -> None:
        now = datetime.now(timezone.utc)
        session = MagicMock(spec=Session)
        session.id = uuid4()
        session.user_id = self.user_id
        session.revoked_at = None
        session.revocation_reason = None
        session.expires_at = now + timedelta(days=3)
        session.last_activity_at = now - timedelta(minutes=5)
        session.trusted_device_id = None
        original_expiry = session.expires_at
        self.uow.sessions.get_by_refresh_token_hash.return_value = session

        tokens = await self.service.refresh("old-refresh-token")

        self.assertEqual(session.refresh_token_hash, hash_token(tokens.refresh_token))
        self.assertNotEqual(tokens.refresh_token, "old-refresh-token")
        self.assertEqual(session.expires_at, original_expiry)
        self.assertLess(tokens.refresh_max_age, 3 * 24 * 60 * 60)
        self.uow.commit.assert_awaited_once()

    async def test_idle_refresh_revokes_session_and_rejects_it(self) -> None:
        now = datetime.now(timezone.utc)
        session = MagicMock(spec=Session)
        session.revoked_at = None
        session.expires_at = now + timedelta(days=3)
        session.last_activity_at = now - timedelta(minutes=61)
        self.uow.sessions.get_by_refresh_token_hash.return_value = session

        with self.assertRaises(AuthenticationError):
            await self.service.refresh("refresh-token")

        self.assertEqual(session.revocation_reason, "idle_timeout")
        self.assertIsNotNone(session.revoked_at)
        self.uow.commit.assert_awaited_once()

    @patch("app.infrastructure.security.tokens._signing_key", return_value="s" * 48)
    async def test_authenticated_activity_updates_session_activity(
        self, _signing_key
    ) -> None:
        session = MagicMock(spec=Session)
        session.id = uuid4()
        session.user_id = self.user_id
        session.revoked_at = None
        session.expires_at = datetime.now(timezone.utc) + timedelta(days=2)
        session.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        session.trusted_device_id = None
        token, _ = create_access_token(self.user_id, session.id)
        self.uow.sessions.get_by_id.return_value = session

        authenticated_user = await self.service.authenticate_access_token(token)

        self.assertIs(authenticated_user, self.user)
        self.uow.commit.assert_awaited_once()
        self.assertGreater(
            session.last_activity_at,
            datetime.now(timezone.utc) - timedelta(seconds=5),
        )

    @patch("app.infrastructure.security.tokens._signing_key", return_value="s" * 48)
    async def test_authenticated_activity_skips_recent_activity_write(
        self, _signing_key
    ) -> None:
        activity = datetime.now(timezone.utc) - timedelta(minutes=1)
        session = MagicMock(spec=Session)
        session.id = uuid4()
        session.user_id = self.user_id
        session.revoked_at = None
        session.expires_at = datetime.now(timezone.utc) + timedelta(days=2)
        session.last_activity_at = activity
        session.trusted_device_id = None
        token, _ = create_access_token(self.user_id, session.id)
        self.uow.sessions.get_by_id.return_value = session

        await self.service.authenticate_access_token(token)

        self.assertEqual(session.last_activity_at, activity)
        self.uow.commit.assert_not_awaited()

    async def test_login_rate_limit_rejects_before_password_lookup(self) -> None:
        self.uow.login_attempts.is_blocked.return_value = True

        with self.assertRaises(AuthenticationError):
            await self.service.login(
                LoginData(
                    email="user@example.com",
                    password="incorrect",
                    client_ip="203.0.113.8",
                )
            )

        self.uow.users.get_by_email.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_revoke_trusted_device_revokes_its_sessions(self) -> None:
        device_id = uuid4()
        device = MagicMock()
        device.id = device_id
        device.user_id = self.user_id
        device.device_token_hash = hash_token("device-secret")
        device.revoked_at = None
        self.uow.trusted_devices.get_by_id.return_value = device

        token_matches = await self.service.revoke_trusted_device(
            self.user_id,
            device_id,
            presented_token="device-secret",
        )

        self.assertTrue(token_matches)
        self.assertEqual(device.revocation_reason, "user_revoked")
        self.uow.sessions.revoke_active_for_device.assert_awaited_once()
        self.uow.commit.assert_awaited_once()

    async def test_revoke_session_is_scoped_to_its_owner(self) -> None:
        session = MagicMock(spec=Session)
        session.user_id = self.user_id
        session.revoked_at = None
        self.uow.sessions.get_by_id.return_value = session

        with self.assertRaises(ResourceNotFoundError):
            await self.service.revoke_session(uuid4(), uuid4())

        self.uow.commit.assert_not_awaited()
