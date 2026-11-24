from uuid import UUID
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.base import BaseRepository
from app.infrastructure.database.models.trusted_device import TrustedDevice

class TrustedDeviceRepository(BaseRepository[TrustedDevice, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=TrustedDevice)

    async def get_by_device_token_hash(self, device_token_hash: str) -> TrustedDevice | None:
        query = (
            select(TrustedDevice)
            .where(TrustedDevice.device_token_hash == device_token_hash)
            .with_for_update(of=TrustedDevice)
        )
        return await self.session.scalar(query)
    
    async def get_by_user_id(self, user_id: UUID) -> list[TrustedDevice]:
        query = (
            select(TrustedDevice)
            .where(TrustedDevice.user_id == user_id)
            .order_by(TrustedDevice.created_at.desc(), TrustedDevice.id)
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
            update(TrustedDevice)
            .where(
                TrustedDevice.user_id == user_id,
                TrustedDevice.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revocation_reason=reason)
        )
        await self.session.execute(query)