from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.infrastructure.database.models.site_link import SiteLink
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.repositories.base import BaseRepository


class SiteSettingsRepository(BaseRepository[SiteSettings, int]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=SiteSettings)

    async def get_singleton(self, *, for_update: bool = False) -> SiteSettings | None:
        query = select(SiteSettings).where(SiteSettings.id == 1)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query)


class SiteLinkRepository(BaseRepository[SiteLink, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=SiteLink)

    async def list_ordered(self) -> list[SiteLink]:
        result = await self.session.scalars(
            select(SiteLink).order_by(
                SiteLink.display_order,
                SiteLink.created_at,
                SiteLink.id,
            )
        )
        return list(result.all())

    async def delete_except(self, link_ids: set[UUID]) -> None:
        query = delete(SiteLink)
        if link_ids:
            query = query.where(SiteLink.id.not_in(link_ids))
        await self.session.execute(query)
        await self.session.flush()
