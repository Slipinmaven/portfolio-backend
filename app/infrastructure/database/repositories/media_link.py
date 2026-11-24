from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.media_link import MediaLink
from app.infrastructure.database.repositories.base import BaseRepository


class MediaLinkRepository(BaseRepository[MediaLink, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=MediaLink)

    async def get_by_media_and_url(
        self,
        media_id: UUID,
        url: str,
    ) -> MediaLink | None:
        query = select(MediaLink).where(
            MediaLink.media_id == media_id,
            MediaLink.url == url,
        )
        return await self.session.scalar(query)

    async def list_by_media_id(self, media_id: UUID) -> list[MediaLink]:
        query = (
            select(MediaLink)
            .where(MediaLink.media_id == media_id)
            .order_by(MediaLink.display_order, MediaLink.created_at, MediaLink.id)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def delete_by_media_id(self, media_id: UUID) -> None:
        await self.session.execute(
            delete(MediaLink).where(MediaLink.media_id == media_id)
        )
