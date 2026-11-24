import asyncio
import unittest
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth.service import AuthService
from app.infrastructure.database.repositories.user import UserRepository
from app.infrastructure.database.unit_of_work.authentication import AuthenticationUnitOfWork
from app.presentation.dependencies.database import get_auth_unit_of_work
from app.presentation.dependencies.services import get_auth_service


class DependencyTests(unittest.TestCase):
    def test_auth_uow_caches_repository_and_service_shares_auth_uow(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        unit_of_work = get_auth_unit_of_work(session=session)

        service = get_auth_service(unit_of_work=unit_of_work)

        self.assertIsInstance(service, AuthService)
        self.assertIs(service.uow, unit_of_work)
        self.assertIsInstance(unit_of_work.users, UserRepository)
        self.assertIs(unit_of_work.users, unit_of_work.users)
        self.assertIs(unit_of_work.users.session, session)

    def test_auth_uow_controls_session_transaction(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            unit_of_work = AuthenticationUnitOfWork(session=session)

            await unit_of_work.commit()
            await unit_of_work.rollback()

            session.commit.assert_awaited_once()
            session.rollback.assert_awaited_once()

        asyncio.run(run())

    def test_auth_uow_commits_when_context_exits_successfully(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            unit_of_work = AuthenticationUnitOfWork(session=session)

            async with unit_of_work:
                pass

            session.commit.assert_awaited_once()
            session.rollback.assert_not_awaited()

        asyncio.run(run())

    def test_auth_uow_rolls_back_when_context_exits_with_exception(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            unit_of_work = AuthenticationUnitOfWork(session=session)

            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                async with unit_of_work:
                    raise RuntimeError("operation failed")

            session.rollback.assert_awaited_once()
            session.commit.assert_not_awaited()

        asyncio.run(run())

    def test_auth_uow_rolls_back_if_commit_fails(self) -> None:
        async def run() -> None:
            session = AsyncMock(spec=AsyncSession)
            session.commit.side_effect = RuntimeError("commit failed")
            unit_of_work = AuthenticationUnitOfWork(session=session)

            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                async with unit_of_work:
                    pass

            session.commit.assert_awaited_once()
            session.rollback.assert_awaited_once()

        asyncio.run(run())
