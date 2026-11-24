from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.errors import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
)
from app.application.users.dto import CreateEditorData, UpdateUserData
from app.core.logging import get_security_logger
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.authentication import (
    AuthenticationUnitOfWork,
)
from app.infrastructure.security.passwords import hash_password

security_logger = get_security_logger()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _role_value(role: UserRole | str) -> str:
    return getattr(role, "value", role)


class UserService:
    def __init__(self, unit_of_work: AuthenticationUnitOfWork) -> None:
        self.uow = unit_of_work

    async def _record_user_audit(
        self,
        *,
        actor_id: UUID,
        action: str,
        user_id: UUID,
        changed_fields: list[str],
    ) -> None:
        await self.uow.audit_logs.create(
            AuditLog(
                user_id=actor_id,
                action=action,
                entity_type="user",
                entity_id=user_id,
                new_values={"changed_fields": changed_fields},
                status="success",
            )
        )

    async def list_users(
        self,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        return await self.uow.users.list_users(offset=offset, limit=limit)

    async def create_editor(self, data: CreateEditorData) -> User:
        email = normalize_email(data.email)
        if await self.uow.users.get_by_email(email):
            raise ConflictError("A user with this email already exists.")

        user = User(
            email=email,
            password_hash=await hash_password(data.password),
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            role=UserRole.EDITOR,
            is_active=True,
        )

        try:
            await self.uow.users.create(user)
            await self._record_user_audit(
                actor_id=UUID(data.created_by_admin_id),
                action="user.editor_created",
                user_id=user.id,
                changed_fields=[
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "is_active",
                ],
            )
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            if await self.uow.users.get_by_email(email):
                raise ConflictError(
                    "A user with this email already exists."
                ) from exc
            raise

        security_logger.info(
            "Editor account created",
            extra={
                "event": "user.editor_created",
                "user_id": user.id,
                "created_by_user_id": data.created_by_admin_id,
            },
        )
        return user

    async def update_profile(
        self,
        user_id: UUID,
        data: UpdateUserData,
        *,
        actor_id: UUID,
        editor_only: bool = False,
    ) -> User:
        user = await self.uow.users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User not found.")
        if editor_only and _role_value(user.role) != UserRole.EDITOR.value:
            raise AuthorizationError("Admins can only edit editor accounts here.")

        updated_email = normalize_email(data.email) if data.email is not None else None
        if updated_email is not None and updated_email != user.email:
            existing_user = await self.uow.users.get_by_email(updated_email)
            if existing_user is not None and existing_user.id != user.id:
                raise ConflictError("A user with this email already exists.")

        changed_fields: list[str] = []
        if updated_email is not None and updated_email != user.email:
            user.email = updated_email
            changed_fields.append("email")
        if data.first_name is not None and data.first_name != user.first_name:
            user.first_name = data.first_name.strip()
            changed_fields.append("first_name")
        if data.last_name is not None and data.last_name != user.last_name:
            user.last_name = data.last_name.strip()
            changed_fields.append("last_name")
        if data.password is not None:
            user.password_hash = await hash_password(data.password)
            changed_fields.append("password")

        try:
            if data.password is not None:
                now = datetime.now(timezone.utc)
                await self.uow.sessions.revoke_active_for_user(
                    user.id,
                    revoked_at=now,
                    reason="password_changed",
                )
                await self.uow.trusted_devices.revoke_active_for_user(
                    user.id,
                    revoked_at=now,
                    reason="password_changed",
                )
            if changed_fields:
                await self._record_user_audit(
                    actor_id=actor_id,
                    action="user.profile_updated",
                    user_id=user.id,
                    changed_fields=changed_fields,
                )
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            if updated_email is not None:
                conflicting_user = await self.uow.users.get_by_email(updated_email)
                if conflicting_user is not None and conflicting_user.id != user.id:
                    raise ConflictError(
                        "A user with this email already exists."
                    ) from exc
            raise

        security_logger.info(
            "User profile updated",
            extra={
                "event": "user.profile_updated",
                "user_id": user.id,
                "created_by_user_id": actor_id,
                "changed_fields": changed_fields,
            },
        )
        return user

    async def delete_editor(self, user_id: UUID, *, actor_id: UUID) -> None:
        user = await self.uow.users.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("User not found.")
        if _role_value(user.role) != UserRole.EDITOR.value:
            raise AuthorizationError("Admins can only delete editor accounts.")

        try:
            await self.uow.users.delete_account(user)
            await self._record_user_audit(
                actor_id=actor_id,
                action="user.editor_deleted",
                user_id=user.id,
                changed_fields=["account"],
            )
            await self.uow.commit()
        except BaseException:
            await self.uow.rollback()
            raise

        security_logger.info(
            "Editor account deleted",
            extra={
                "event": "user.editor_deleted",
                "user_id": user_id,
                "created_by_user_id": actor_id,
            },
        )
