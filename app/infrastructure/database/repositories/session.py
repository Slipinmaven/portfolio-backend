from uuid import UUID

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.session import Session
from app.infrastructure.database.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Session)

    async def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        query = (
            select(Session)
            .where(Session.refresh_token_hash == token_hash)
            .with_for_update(of=Session)
        )
        return await self.session.scalar(query)

    async def get_by_user_id(self, user_id: UUID) -> list[Session]:
        query = (
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.created_at.desc(), Session.id)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def revoke_active_for_user(
        self,
        user_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
    ) -> None:
        query = (
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=revoked_at, revocation_reason=reason)
        )
        await self.session.execute(query)

    async def revoke_active_for_device(
        self,
        device_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
    ) -> None:
        query = (
            update(Session)
            .where(
                Session.trusted_device_id == device_id,
                Session.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revocation_reason=reason)
        )
        await self.session.execute(query)
