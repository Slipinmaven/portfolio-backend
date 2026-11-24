from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.enums import PageRevisionState, PageStatus
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_media import PageMedia
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.repositories.base import BaseRepository


class PageMediaRepository(BaseRepository[PageMedia, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=PageMedia)

    async def replace_for_page(
        self,
        page_id: UUID,
        media_ids: set[UUID],
    ) -> None:
        await self.session.execute(
            delete(PageMedia).where(PageMedia.page_id == page_id)
        )
        if media_ids:
            self.session.add_all(
                PageMedia(page_id=page_id, media_id=media_id)
                for media_id in media_ids
            )
        await self.session.flush()

    async def list_media_ids(self, page_id: UUID) -> set[UUID]:
        result = await self.session.scalars(
            select(PageMedia.media_id).where(PageMedia.page_id == page_id)
        )
        return set(result.all())

    async def list_published_sections_for_media(
        self,
        media_id: UUID,
    ) -> list[list[dict[str, object]]]:
        query = (
            select(PageRevision.sections)
            .join(PageMedia, PageMedia.page_id == PageRevision.page_id)
            .join(Page, Page.id == PageRevision.page_id)
            .where(
                PageMedia.media_id == media_id,
                Page.status == PageStatus.PUBLISHED,
                PageRevision.state == PageRevisionState.PUBLISHED,
            )
        )
        result = await self.session.scalars(query)
        return list(result.all())
