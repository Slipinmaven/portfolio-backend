from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.media import MediaRepository
from app.infrastructure.database.repositories.page import (
    PageRepository,
    PageRevisionRepository,
)
from app.infrastructure.database.repositories.page_media import PageMediaRepository
from app.infrastructure.database.repositories.post import PostRepository
from app.infrastructure.database.repositories.project import ProjectRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class PagesUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._pages: PageRepository | None = None
        self._revisions: PageRevisionRepository | None = None
        self._page_media: PageMediaRepository | None = None
        self._audit_logs: AuditLogRepository | None = None
        self._media: MediaRepository | None = None
        self._projects: ProjectRepository | None = None
        self._posts: PostRepository | None = None

    @property
    def pages(self) -> PageRepository:
        if self._pages is None:
            self._pages = PageRepository(session=self.session)
        return self._pages

    @property
    def revisions(self) -> PageRevisionRepository:
        if self._revisions is None:
            self._revisions = PageRevisionRepository(session=self.session)
        return self._revisions

    @property
    def page_media(self) -> PageMediaRepository:
        if self._page_media is None:
            self._page_media = PageMediaRepository(session=self.session)
        return self._page_media

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
    def posts(self) -> PostRepository:
        if self._posts is None:
            self._posts = PostRepository(session=self.session)
        return self._posts
