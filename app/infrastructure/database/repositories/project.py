from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import (
    DevelopmentStatus,
    ProjectMediaRole,
    ProjectStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.models.project_resource import ProjectResource
from app.infrastructure.database.models.tag import Tag
from app.infrastructure.database.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Project)

    async def get_by_slug(self, slug: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.slug == slug))

    async def get_by_ids(self, project_ids: list[UUID]) -> list[Project]:
        if not project_ids:
            return []
        result = await self.session.scalars(
            select(Project).where(Project.id.in_(project_ids))
        )
        return list(result.all())

    async def get_published_by_ids(self, project_ids: list[UUID]) -> list[Project]:
        if not project_ids:
            return []
        result = await self.session.scalars(
            select(Project).where(
                Project.id.in_(project_ids),
                Project.status == ProjectStatus.PUBLISHED,
            )
        )
        return list(result.all())

    async def list_featured_published(self, *, limit: int) -> list[Project]:
        query = (
            select(Project)
            .where(
                Project.status == ProjectStatus.PUBLISHED,
                Project.is_featured.is_(True),
            )
            .order_by(
                Project.display_order,
                Project.title,
                Project.id,
            )
            .limit(limit)
        )
        return list((await self.session.scalars(query)).all())

    async def get_with_associations_by_id(self, project_id: UUID) -> Project | None:
        query = (
            select(Project)
            .options(
                selectinload(Project.categories),
                selectinload(Project.tags),
                selectinload(Project.resource_associations).selectinload(
                    ProjectResource.resource
                ),
                selectinload(Project.media_associations)
                .selectinload(ProjectMedia.media)
                .selectinload(Media.links),
            )
            .where(Project.id == project_id)
        )
        return await self.session.scalar(query)

    async def get_published_by_slug(self, slug: str) -> Project | None:
        query = (
            select(Project)
            .options(
                selectinload(Project.categories),
                selectinload(Project.tags),
                selectinload(Project.resource_associations).selectinload(
                    ProjectResource.resource
                ),
                selectinload(Project.media_associations)
                .selectinload(ProjectMedia.media)
                .selectinload(Media.links),
            )
            .where(
                Project.slug == slug,
                Project.status == ProjectStatus.PUBLISHED,
            )
        )
        return await self.session.scalar(query)

    async def get_project_covers(
        self,
        project_ids: list[UUID],
    ) -> dict[UUID, ProjectMedia]:
        if not project_ids:
            return {}
        result = await self.session.scalars(
            select(ProjectMedia)
            .options(selectinload(ProjectMedia.media))
            .where(
                ProjectMedia.project_id.in_(project_ids),
                ProjectMedia.role == ProjectMediaRole.COVER,
            )
        )
        return {
            association.project_id: association
            for association in result.all()
        }

    async def list_projects(
        self,
        *,
        offset: int,
        limit: int,
        status: ProjectStatus | None = None,
        development_status: DevelopmentStatus | None = None,
        is_featured: bool | None = None,
        category_id: UUID | None = None,
        tag_id: UUID | None = None,
        active_catalog_only: bool = False,
    ) -> tuple[list[Project], int]:
        filters = []
        if status is not None:
            filters.append(Project.status == status)
        if development_status is not None:
            filters.append(Project.development_status == development_status)
        if is_featured is not None:
            filters.append(Project.is_featured == is_featured)
        if category_id is not None:
            category_filter = [Category.id == category_id]
            if active_catalog_only:
                category_filter.append(Category.is_active.is_(True))
            filters.append(
                Project.categories.any(and_(*category_filter))  # type: ignore[arg-type]
            )
        if tag_id is not None:
            tag_filter = [Tag.id == tag_id]
            if active_catalog_only:
                tag_filter.append(Tag.is_active.is_(True))
            filters.append(
                Project.tags.any(and_(*tag_filter))  # type: ignore[arg-type]
            )

        query = (
            select(Project)
            .where(*filters)
            .order_by(
                Project.display_order,
                Project.created_at.desc(),
                Project.id,
            )
            .offset(offset)
            .limit(limit)
        )
        projects = list((await self.session.scalars(query)).all())
        total_query = select(func.count()).select_from(Project).where(*filters)
        total = await self.session.scalar(total_query)
        return projects, total or 0
