import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.dto import LoginData
from app.application.auth.service import AuthService
from app.application.errors import AuthenticationError
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.authentication import AuthenticationUnitOfWork
from app.infrastructure.security.passwords import hash_password, verify_password


class PasswordHashTests(unittest.IsolatedAsyncioTestCase):
    async def test_hash_is_salted_and_verifies_password(self) -> None:
        password = "correct horse battery staple"
        first_hash = await hash_password(password)
        second_hash = await hash_password(password)

        self.assertTrue(first_hash.startswith("$argon2id$"))
        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(await verify_password(password, first_hash))
        self.assertFalse(await verify_password("wrong password", first_hash))


class AuthLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_verifies_password_and_returns_user(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = None
        user = MagicMock(spec=User)
        user.password_hash = await hash_password("correct password")
        user.is_active = True
        session.scalar.return_value = user
        service = AuthService(AuthenticationUnitOfWork(session=session))
        sessions = service.uow.sessions

        async def persist_session(login_session) -> None:
            login_session.id = uuid4()

        sessions.create = AsyncMock(side_effect=persist_session)
        service.uow.commit = AsyncMock()

        with patch(
            "app.application.auth.service.create_access_token",
            return_value=("test-access-token", 900),
        ):
            result = await service.login(
                LoginData(
                    email="USER@example.com",
                    password="correct password",
                    client_ip="203.0.113.8",
                )
            )

        self.assertEqual(result.user_id, str(user.id))
        session.scalar.assert_awaited_once()

    async def test_login_rejects_invalid_password(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = None
        user = MagicMock(spec=User)
        user.password_hash = await hash_password("correct password")
        user.is_active = True
        session.scalar.return_value = user
        service = AuthService(AuthenticationUnitOfWork(session=session))

        with self.assertRaises(AuthenticationError):
            await service.login(
                LoginData(email="user@example.com", password="wrong password")
            )

    async def test_login_rejects_unknown_email(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = None
        session.scalar.return_value = None
        service = AuthService(AuthenticationUnitOfWork(session=session))

        with self.assertRaises(AuthenticationError):
            await service.login(
                LoginData(email="unknown@example.com", password="any password")
            )

    async def test_login_rejects_inactive_user(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.get.return_value = None
        user = MagicMock(spec=User)
        user.is_active = False
        session.scalar.return_value = user
        service = AuthService(AuthenticationUnitOfWork(session=session))

        with self.assertRaises(AuthenticationError):
            await service.login(
                LoginData(email="user@example.com", password="any password")
            )
