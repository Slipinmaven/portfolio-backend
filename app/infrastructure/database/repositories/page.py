from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.enums import PageStatus
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.repositories.base import BaseRepository


class PageRepository(BaseRepository[Page, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Page)

    async def get_by_slug(self, slug: str) -> Page | None:
        return await self.session.scalar(select(Page).where(Page.slug == slug))

    async def get_by_ids(self, page_ids: list[UUID]) -> list[Page]:
        if not page_ids:
            return []
        result = await self.session.scalars(
            select(Page).where(Page.id.in_(page_ids))
        )
        return list(result.all())

    async def get_published_by_ids(self, page_ids: list[UUID]) -> list[Page]:
        if not page_ids:
            return []
        result = await self.session.scalars(
            select(Page).where(
                Page.id.in_(page_ids),
                Page.status == PageStatus.PUBLISHED,
            )
        )
        return list(result.all())

    async def get_published_by_slug(self, slug: str) -> Page | None:
        query = (
            select(Page)
            .options(selectinload(Page.revisions))
            .where(Page.slug == slug, Page.status == PageStatus.PUBLISHED)
        )
        return await self.session.scalar(query)

    async def get_with_revisions_by_id(
        self,
        page_id: UUID,
        *,
        for_update: bool = False,
    ) -> Page | None:
        query = (
            select(Page)
            .options(selectinload(Page.revisions))
            .where(Page.id == page_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update(of=Page)
        return await self.session.scalar(query)

    async def list_pages(
        self,
        *,
        offset: int,
        limit: int,
        status: PageStatus | None = None,
    ) -> tuple[list[Page], int]:
        filters = [Page.status == status] if status is not None else []
        query = (
            select(Page)
            .options(selectinload(Page.revisions))
            .where(*filters)
            .order_by(
                Page.system_key.is_(None),
                Page.system_key,
                Page.created_at.desc(),
                Page.id,
            )
            .offset(offset)
            .limit(limit)
        )
        pages = list((await self.session.scalars(query)).all())
        total = await self.session.scalar(
            select(func.count()).select_from(Page).where(*filters)
        )
        return pages, total or 0


class PageRevisionRepository(BaseRepository[PageRevision, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=PageRevision)

    async def get_by_page_and_state(
        self,
        page_id: UUID,
        state: str,
    ) -> PageRevision | None:
        query = select(PageRevision).where(
            PageRevision.page_id == page_id,
            PageRevision.state == state,
        )
        return await self.session.scalar(query)

    async def get_for_page(
        self,
        page_id: UUID,
        revision_id: UUID,
    ) -> PageRevision | None:
        query = select(PageRevision).where(
            PageRevision.page_id == page_id,
            PageRevision.id == revision_id,
        )
        return await self.session.scalar(query)

    async def list_for_page(self, page_id: UUID) -> list[PageRevision]:
        query = (
            select(PageRevision)
            .where(PageRevision.page_id == page_id)
            .order_by(PageRevision.revision_number.desc())
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_active_for_page(self, page_id: UUID) -> list[PageRevision]:
        query = (
            select(PageRevision)
            .where(
                PageRevision.page_id == page_id,
                PageRevision.state.in_(("DRAFT", "PUBLISHED")),
            )
            .order_by(PageRevision.revision_number)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def latest_revision_number(self, page_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.max(PageRevision.revision_number)).where(
                PageRevision.page_id == page_id
            )
        )
        return value or 0

    async def delete_draft(self, revision: PageRevision) -> None:
        await self.session.delete(revision)
        await self.session.flush()
