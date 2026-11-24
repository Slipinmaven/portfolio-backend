import json
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from app.application.errors import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
)
from app.application.users.dto import CreateEditorData, UpdateUserData
from app.application.users.service import UserService
from app.core.logging import StructuredFormatter
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.authentication import AuthenticationUnitOfWork


class UserServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_user_model_normalizes_email_on_assignment(self) -> None:
        user = User(
            email="  EDITOR@Example.COM ",
            password_hash="hashed",
            first_name="Editor",
            last_name="Person",
        )

        self.assertEqual(user.email, "editor@example.com")

    def setUp(self) -> None:
        self.uow = MagicMock(spec=AuthenticationUnitOfWork)
        self.uow.users = MagicMock()
        self.uow.users.get_by_email = AsyncMock(return_value=None)

        async def persist(user: User) -> User:
            user.id = uuid4()
            return user

        self.uow.users.create = AsyncMock(side_effect=persist)
        self.uow.users.get_by_id = AsyncMock()
        self.uow.users.list_users = AsyncMock(return_value=([], 0))
        self.uow.users.delete_account = AsyncMock()
        self.uow.audit_logs = MagicMock()
        self.uow.audit_logs.create = AsyncMock()
        self.uow.commit = AsyncMock()
        self.uow.rollback = AsyncMock()
        self.uow.sessions = MagicMock()
        self.uow.sessions.revoke_active_for_user = AsyncMock()
        self.uow.trusted_devices = MagicMock()
        self.uow.trusted_devices.revoke_active_for_user = AsyncMock()
        self.service = UserService(self.uow)
        self.data = CreateEditorData(
            email=" EDITOR@example.com ",
            password="long-enough-password",
            first_name=" Editor ",
            last_name=" Person ",
            created_by_admin_id=str(uuid4()),
        )

    async def test_create_editor_normalizes_and_persists_editor_role(self) -> None:
        user = await self.service.create_editor(self.data)

        self.assertEqual(user.email, "editor@example.com")
        self.assertEqual(user.first_name, "Editor")
        self.assertEqual(user.last_name, "Person")
        self.assertEqual(user.role, UserRole.EDITOR)
        self.assertNotEqual(user.password_hash, self.data.password)
        self.uow.users.create.assert_awaited_once_with(user)
        self.uow.audit_logs.create.assert_awaited_once()
        audit_log = self.uow.audit_logs.create.await_args.args[0]
        self.assertIsInstance(audit_log, AuditLog)
        self.assertEqual(audit_log.user_id, UUID(self.data.created_by_admin_id))
        self.assertEqual(audit_log.action, "user.editor_created")
        self.assertEqual(audit_log.entity_id, user.id)
        self.assertEqual(
            audit_log.new_values,
            {
                "changed_fields": [
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "is_active",
                ]
            },
        )
        self.assertNotIn("password", str(audit_log.new_values))
        self.uow.commit.assert_awaited_once()

    async def test_create_editor_rejects_existing_email(self) -> None:
        self.uow.users.get_by_email.return_value = MagicMock(spec=User)

        with self.assertRaises(ConflictError):
            await self.service.create_editor(self.data)

        self.uow.users.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_update_profile_changes_email_and_password_and_revokes_sessions(self) -> None:
        user = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="old-hash",
            first_name="Editor",
            last_name="Person",
            role=UserRole.EDITOR,
            is_active=True,
        )
        self.uow.users.get_by_id.return_value = user
        actor_id = uuid4()

        updated_user = await self.service.update_profile(
            user.id,
            UpdateUserData(
                email=" New.Email@Example.com ",
                first_name="Updated",
                password="new-secure-password",
            ),
            actor_id=actor_id,
        )

        self.assertIs(updated_user, user)
        self.assertEqual(user.email, "new.email@example.com")
        self.assertEqual(user.first_name, "Updated")
        self.assertNotEqual(user.password_hash, "old-hash")
        self.uow.sessions.revoke_active_for_user.assert_awaited_once()
        self.uow.trusted_devices.revoke_active_for_user.assert_awaited_once()
        self.assertEqual(
            self.uow.trusted_devices.revoke_active_for_user.await_args.kwargs[
                "reason"
            ],
            "password_changed",
        )
        self.assertEqual(
            self.uow.trusted_devices.revoke_active_for_user.await_args.args[0],
            user.id,
        )
        self.uow.audit_logs.create.assert_awaited_once()
        audit_log = self.uow.audit_logs.create.await_args.args[0]
        self.assertEqual(audit_log.user_id, actor_id)
        self.assertEqual(audit_log.action, "user.profile_updated")
        self.assertEqual(audit_log.entity_id, user.id)
        self.assertEqual(
            audit_log.new_values,
            {"changed_fields": ["email", "first_name", "password"]},
        )
        self.assertNotIn("new-password", str(audit_log.new_values))
        self.uow.commit.assert_awaited_once()

    async def test_admin_profile_update_cannot_target_another_admin(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        self.uow.users.get_by_id.return_value = admin

        with self.assertRaises(AuthorizationError):
            await self.service.update_profile(
                admin.id,
                UpdateUserData(first_name="Changed"),
                actor_id=uuid4(),
                editor_only=True,
            )

        self.uow.commit.assert_not_awaited()

    async def test_update_profile_rejects_email_used_by_another_user(self) -> None:
        user = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="Person",
            role=UserRole.EDITOR,
            is_active=True,
        )
        existing = User(
            id=uuid4(),
            email="taken@example.com",
            password_hash="hashed",
            first_name="Other",
            last_name="Person",
            role=UserRole.EDITOR,
            is_active=True,
        )
        self.uow.users.get_by_id.return_value = user
        self.uow.users.get_by_email.return_value = existing

        with self.assertRaises(ConflictError):
            await self.service.update_profile(
                user.id,
                UpdateUserData(email="taken@example.com"),
                actor_id=user.id,
            )

        self.uow.commit.assert_not_awaited()

    async def test_list_users_delegates_pagination_to_repository(self) -> None:
        users = [MagicMock(spec=User)]
        self.uow.users.list_users.return_value = (users, 23)

        result_users, total = await self.service.list_users(offset=10, limit=5)

        self.assertEqual(result_users, users)
        self.assertEqual(total, 23)
        self.uow.users.list_users.assert_awaited_once_with(offset=10, limit=5)

    async def test_delete_editor_deletes_and_commits(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        self.uow.users.get_by_id.return_value = editor
        actor_id = uuid4()

        await self.service.delete_editor(editor.id, actor_id=actor_id)

        self.uow.users.delete_account.assert_awaited_once_with(editor)
        self.uow.audit_logs.create.assert_awaited_once()
        audit_log = self.uow.audit_logs.create.await_args.args[0]
        self.assertEqual(audit_log.user_id, actor_id)
        self.assertEqual(audit_log.action, "user.editor_deleted")
        self.assertEqual(audit_log.entity_id, editor.id)
        self.assertEqual(audit_log.new_values, {"changed_fields": ["account"]})
        self.uow.commit.assert_awaited_once()

    async def test_delete_editor_rejects_admin_account(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        self.uow.users.get_by_id.return_value = admin

        with self.assertRaises(AuthorizationError):
            await self.service.delete_editor(admin.id, actor_id=uuid4())

        self.uow.users.delete_account.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_delete_editor_rejects_missing_account(self) -> None:
        self.uow.users.get_by_id.return_value = None

        with self.assertRaises(ResourceNotFoundError):
            await self.service.delete_editor(uuid4(), actor_id=uuid4())

        self.uow.users.delete_account.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    def test_security_log_includes_admin_actor_id(self) -> None:
        record = logging.LogRecord(
            name="app.security",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Editor account created",
            args=(),
            exc_info=None,
        )
        record.created_by_user_id = self.data.created_by_admin_id

        payload = json.loads(StructuredFormatter().format(record))

        self.assertEqual(payload["created_by_user_id"], self.data.created_by_admin_id)
