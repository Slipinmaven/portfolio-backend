import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.authentication import (
    AuthenticationUnitOfWork,
)
from app.scripts.create_admin import _prompt_admin_details, create_admin_account


class CreateAdminScriptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.unit_of_work = MagicMock(spec=AuthenticationUnitOfWork)
        self.unit_of_work.users = MagicMock()
        self.unit_of_work.users.get_by_email = AsyncMock(return_value=None)

        async def persist(user: User) -> User:
            user.id = uuid4()
            return user

        self.unit_of_work.users.create = AsyncMock(side_effect=persist)
        self.unit_of_work.audit_logs = MagicMock()
        self.unit_of_work.audit_logs.create = AsyncMock()
        self.unit_of_work.commit = AsyncMock()
        self.unit_of_work.rollback = AsyncMock()

    @patch("app.scripts.create_admin.hash_password", new_callable=AsyncMock)
    async def test_creates_admin_with_hashed_password(
        self,
        hash_password: AsyncMock,
    ) -> None:
        hash_password.return_value = "argon2id-hash"

        user = await create_admin_account(
            self.unit_of_work,
            email=" ADMIN@example.com ",
            password="secret-admin-password",
            first_name=" Admin ",
            last_name=" User ",
        )

        self.assertEqual(user.email, "admin@example.com")
        self.assertEqual(user.role, UserRole.ADMIN)
        self.assertTrue(user.is_active)
        self.assertEqual(user.password_hash, "argon2id-hash")
        hash_password.assert_awaited_once_with("secret-admin-password")
        self.unit_of_work.audit_logs.create.assert_awaited_once()
        audit_log = self.unit_of_work.audit_logs.create.await_args.args[0]
        self.assertIsInstance(audit_log, AuditLog)
        self.assertIsNone(audit_log.user_id)
        self.assertEqual(audit_log.action, "user.admin_created")
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
        self.unit_of_work.commit.assert_awaited_once()

    @patch("app.scripts.create_admin.hash_password", new_callable=AsyncMock)
    async def test_refuses_existing_email(
        self,
        hash_password: AsyncMock,
    ) -> None:
        self.unit_of_work.users.get_by_email.return_value = MagicMock(spec=User)

        with self.assertRaisesRegex(ValueError, "already exists"):
            await create_admin_account(
                self.unit_of_work,
                email="admin@example.com",
                password="secret-admin-password",
                first_name="Admin",
                last_name="User",
            )

        hash_password.assert_not_awaited()
        self.unit_of_work.users.create.assert_not_awaited()

    @patch("app.scripts.create_admin.hash_password", new_callable=AsyncMock)
    async def test_duplicate_email_race_rolls_back(
        self,
        hash_password: AsyncMock,
    ) -> None:
        self.unit_of_work.users.get_by_email.side_effect = [
            None,
            MagicMock(spec=User),
        ]
        self.unit_of_work.users.create.side_effect = IntegrityError(
            "insert", {}, Exception("unique constraint")
        )

        with self.assertRaisesRegex(ValueError, "already exists"):
            await create_admin_account(
                self.unit_of_work,
                email="admin@example.com",
                password="secret-admin-password",
                first_name="Admin",
                last_name="User",
            )

        self.unit_of_work.rollback.assert_awaited_once()

    def test_prompts_for_password_without_echo_and_requires_confirmation(self) -> None:
        with (
            patch(
                "builtins.input",
                side_effect=["admin@example.com", "Admin", "User"],
            ),
            patch(
                "app.scripts.create_admin.getpass",
                side_effect=["secret-admin-password", "secret-admin-password"],
            ) as getpass,
        ):
            details = _prompt_admin_details()

        self.assertEqual(details["email"], "admin@example.com")
        self.assertEqual(details["password"], "secret-admin-password")
        self.assertEqual(getpass.call_count, 2)
