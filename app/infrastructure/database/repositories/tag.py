from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.tag import Tag
from app.infrastructure.database.repositories.base import BaseRepository


class TagRepository(BaseRepository[Tag, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Tag)

    async def get_by_slug(self, slug: str) -> Tag | None:
        return await self.session.scalar(select(Tag).where(Tag.slug == slug))

    async def get_active_by_ids(self, tag_ids: list[UUID]) -> list[Tag]:
        if not tag_ids:
            return []
        query = select(Tag).where(
            Tag.id.in_(tag_ids),
            Tag.is_active.is_(True),
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def delete(self, entity: Tag) -> None:
        statement = (
            delete(Tag)
            .where(Tag.id == entity.id)
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(statement)

    async def list_tags(
        self,
        *,
        offset: int,
        limit: int,
        is_active: bool | None = None,
    ) -> tuple[list[Tag], int]:
        filters = []
        if is_active is not None:
            filters.append(Tag.is_active == is_active)

        query = (
            select(Tag)
            .where(*filters)
            .order_by(Tag.name, Tag.id)
            .offset(offset)
            .limit(limit)
        )
        tags = list((await self.session.scalars(query)).all())
        total_query = select(func.count()).select_from(Tag).where(*filters)
        total = await self.session.scalar(total_query)
        return tags, total or 0
