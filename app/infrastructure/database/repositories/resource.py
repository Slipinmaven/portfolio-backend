from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.enums import ResourceStatus, ResourceType
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.repositories.base import BaseRepository


class ResourceRepository(BaseRepository[Resource, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Resource)

    async def get_by_ids(self, resource_ids: list[UUID]) -> list[Resource]:
        if not resource_ids:
            return []
        result = await self.session.scalars(
            select(Resource).where(Resource.id.in_(resource_ids))
        )
        return list(result.all())

    async def get_by_url(self, url: str) -> Resource | None:
        return await self.session.scalar(
            select(Resource).where(Resource.url == url)
        )

    async def list_resources(
        self,
        *,
        offset: int,
        limit: int,
        status: ResourceStatus | None = None,
        resource_type: ResourceType | None = None,
        published_only: bool = False,
    ) -> tuple[list[Resource], int]:
        from sqlalchemy import func

        filters = []
        if published_only:
            filters.append(Resource.status == ResourceStatus.PUBLISHED)
        elif status is not None:
            filters.append(Resource.status == status)
        if resource_type is not None:
            filters.append(Resource.resource_type == resource_type)

        query = (
            select(Resource)
            .where(*filters)
            .order_by(
                Resource.published_at.desc().nullslast(),
                Resource.title,
                Resource.id,
            )
            .offset(offset)
            .limit(limit)
        )
        resources = list((await self.session.scalars(query)).all())
        total = await self.session.scalar(
            select(func.count()).select_from(Resource).where(*filters)
        )
        return resources, total or 0
