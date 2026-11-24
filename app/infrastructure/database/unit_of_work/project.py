from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.category import CategoryRepository
from app.infrastructure.database.repositories.media import MediaRepository
from app.infrastructure.database.repositories.media_link import MediaLinkRepository
from app.infrastructure.database.repositories.project import ProjectRepository
from app.infrastructure.database.repositories.project_media import (
    ProjectMediaRepository,
)
from app.infrastructure.database.repositories.resource import ResourceRepository
from app.infrastructure.database.repositories.tag import TagRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class ProjectUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._projects: ProjectRepository | None = None
        self._categories: CategoryRepository | None = None
        self._tags: TagRepository | None = None
        self._audit_logs: AuditLogRepository | None = None
        self._media: MediaRepository | None = None
        self._media_links: MediaLinkRepository | None = None
        self._project_media: ProjectMediaRepository | None = None
        self._resources: ResourceRepository | None = None

    @property
    def projects(self) -> ProjectRepository:
        if self._projects is None:
            self._projects = ProjectRepository(session=self.session)
        return self._projects

    @property
    def categories(self) -> CategoryRepository:
        if self._categories is None:
            self._categories = CategoryRepository(session=self.session)
        return self._categories

    @property
    def tags(self) -> TagRepository:
        if self._tags is None:
            self._tags = TagRepository(session=self.session)
        return self._tags

    @property
    def audit_logs(self) -> AuditLogRepository:
        if self._audit_logs is None:
            self._audit_logs = AuditLogRepository(session=self.session)
        return self._audit_logs

    @property
    def media(self) -> MediaRepository:
        if self._media is None:
            self._media = MediaRepository(session=self.session)
        return self._media

    @property
    def media_links(self) -> MediaLinkRepository:
        if self._media_links is None:
            self._media_links = MediaLinkRepository(session=self.session)
        return self._media_links

    @property
    def project_media(self) -> ProjectMediaRepository:
        if self._project_media is None:
            self._project_media = ProjectMediaRepository(session=self.session)
        return self._project_media

    @property
    def resources(self) -> ResourceRepository:
        if self._resources is None:
            self._resources = ResourceRepository(session=self.session)
        return self._resources