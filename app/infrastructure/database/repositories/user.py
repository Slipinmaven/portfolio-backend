from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.session import Session
from app.infrastructure.database.models.trusted_device import TrustedDevice
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=User)

    async def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        return await self.session.scalar(query)

    async def get_by_role(self, role: str) -> list[User]:
        query = select(User).where(User.role == role)
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_users(
        self,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        query = (
            select(User)
            .where(User.role.in_([UserRole.ADMIN.value, UserRole.EDITOR.value]))
            .order_by(User.created_at.desc(), User.id)
            .offset(offset)
            .limit(limit)
        )
        users = list((await self.session.scalars(query)).all())
        total_query = (
            select(func.count())
            .select_from(User)
            .where(User.role.in_([UserRole.ADMIN.value, UserRole.EDITOR.value]))
        )
        total = await self.session.scalar(total_query)
        return users, total or 0

    async def delete_account(self, user: User) -> None:
        await self.session.execute(delete(Session).where(Session.user_id == user.id))
        await self.session.execute(
            delete(TrustedDevice).where(TrustedDevice.user_id == user.id)
        )
        await self.session.execute(
            update(AuditLog)
            .where(AuditLog.user_id == user.id)
            .values(user_id=None)
        )
        await self.session.execute(
            delete(User)
            .where(User.id == user.id)
            .execution_options(synchronize_session=False)
        )
