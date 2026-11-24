from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.category import Category
from app.infrastructure.database.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Category)

    async def get_by_slug(self, slug: str) -> Category | None:
        return await self.session.scalar(select(Category).where(Category.slug == slug))

    async def get_active_by_slug(self, slug: str) -> Category | None:
        return await self.session.scalar(
            select(Category).where(
                Category.slug == slug,
                Category.is_active.is_(True),
            )
        )

    async def list_siblings_for_update(
        self,
        parent_id: UUID | None,
    ) -> list[Category]:
        parent_filter = (
            Category.parent_id.is_(None)
            if parent_id is None
            else Category.parent_id == parent_id
        )
        query = (
            select(Category)
            .where(parent_filter)
            .order_by(Category.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_active_by_ids(self, category_ids: list[UUID]) -> list[Category]:
        if not category_ids:
            return []
        query = select(Category).where(
            Category.id.in_(category_ids),
            Category.is_active.is_(True),
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_by_ids(self, category_ids: list[UUID]) -> list[Category]:
        if not category_ids:
            return []
        result = await self.session.scalars(
            select(Category).where(Category.id.in_(category_ids))
        )
        return list(result.all())

    async def delete(self, entity: Category) -> None:
        statement = (
            delete(Category)
            .where(Category.id == entity.id)
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(statement)

    async def get_children(self, parent_id: UUID) -> list[Category]:
        query = (
            select(Category)
            .where(Category.parent_id == parent_id)
            .order_by(Category.display_order, Category.id)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_categories(
        self,
        *,
        offset: int,
        limit: int,
        is_active: bool | None = None,
    ) -> tuple[list[Category], int]:
        filters = []
        if is_active is not None:
            filters.append(Category.is_active == is_active)

        query = (
            select(Category)
            .where(*filters)
            .order_by(Category.parent_id, Category.display_order, Category.id)
            .offset(offset)
            .limit(limit)
        )
        categories = list((await self.session.scalars(query)).all())
        total_query = select(func.count()).select_from(Category).where(*filters)
        total = await self.session.scalar(total_query)
        return categories, total or 0

    async def get_root_categories(self) -> list[Category]:
        query = (
            select(Category)
            .where(Category.parent_id.is_(None))
            .order_by(Category.display_order, Category.id)
        )
        result = await self.session.scalars(query)
        return list(result.all())
