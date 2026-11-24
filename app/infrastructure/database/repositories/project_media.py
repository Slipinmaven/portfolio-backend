from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.enums import ProjectMediaRole, ProjectStatus
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.repositories.base import BaseRepository


class ProjectMediaRepository(
    BaseRepository[ProjectMedia, tuple[UUID, UUID, ProjectMediaRole]]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=ProjectMedia)

    async def get_cover_for_project(self, project_id: UUID) -> ProjectMedia | None:
        query = select(ProjectMedia).where(
            ProjectMedia.project_id == project_id,
            ProjectMedia.role == ProjectMediaRole.COVER,
        )
        return await self.session.scalar(query)

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        role: ProjectMediaRole | None = None,
    ) -> list[ProjectMedia]:
        filters = [ProjectMedia.project_id == project_id]
        if role is not None:
            filters.append(ProjectMedia.role == role)

        query = (
            select(ProjectMedia)
            .options(selectinload(ProjectMedia.media).selectinload(Media.links))
            .where(*filters)
            .order_by(
                ProjectMedia.role,
                ProjectMedia.display_order,
                ProjectMedia.media_id,
            )
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_by_media(self, media_id: UUID) -> list[ProjectMedia]:
        query = (
            select(ProjectMedia)
            .options(selectinload(ProjectMedia.project))
            .where(ProjectMedia.media_id == media_id)
            .order_by(ProjectMedia.project_id, ProjectMedia.role)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def has_published_usage(self, media_id: UUID) -> bool:
        query = select(
            exists().where(
                ProjectMedia.media_id == media_id,
                ProjectMedia.project_id == Project.id,
                Project.status == ProjectStatus.PUBLISHED,
            )
        )
        return bool(await self.session.scalar(query))

    async def get_association(
        self,
        project_id: UUID,
        media_id: UUID,
        role: ProjectMediaRole,
    ) -> ProjectMedia | None:
        query = (
            select(ProjectMedia)
            .options(selectinload(ProjectMedia.media).selectinload(Media.links))
            .where(
                ProjectMedia.project_id == project_id,
                ProjectMedia.media_id == media_id,
                ProjectMedia.role == role,
            )
        )
        return await self.session.scalar(query)

    async def delete_association(
        self,
        project_id: UUID,
        media_id: UUID,
        role: ProjectMediaRole,
    ) -> None:
        statement = delete(ProjectMedia).where(
            ProjectMedia.project_id == project_id,
            ProjectMedia.media_id == media_id,
            ProjectMedia.role == role,
        )
        await self.session.execute(statement)
