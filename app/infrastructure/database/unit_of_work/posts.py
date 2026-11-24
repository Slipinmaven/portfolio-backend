from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.category import CategoryRepository
from app.infrastructure.database.repositories.post import PostRepository
from app.infrastructure.database.repositories.media import MediaRepository
from app.infrastructure.database.repositories.project import ProjectRepository
from app.infrastructure.database.repositories.resource import ResourceRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class PostsUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._posts: PostRepository | None = None
        self._categories: CategoryRepository | None = None
        self._audit_logs: AuditLogRepository | None = None
        self._media: MediaRepository | None = None
        self._projects: ProjectRepository | None = None
        self._resources: ResourceRepository | None = None

    @property
    def posts(self) -> PostRepository:
        if self._posts is None:
            self._posts = PostRepository(session=self.session)
        return self._posts

    @property
    def categories(self) -> CategoryRepository:
        if self._categories is None:
            self._categories = CategoryRepository(session=self.session)
        return self._categories

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
    def projects(self) -> ProjectRepository:
        if self._projects is None:
            self._projects = ProjectRepository(session=self.session)
        return self._projects

    @property
    def resources(self) -> ResourceRepository:
        if self._resources is None:
            self._resources = ResourceRepository(session=self.session)
        return self._resources
