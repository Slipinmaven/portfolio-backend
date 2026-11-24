from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.category import CategoryRepository
from app.infrastructure.database.repositories.navigation import NavigationRepository
from app.infrastructure.database.repositories.page import PageRepository
from app.infrastructure.database.repositories.post import PostRepository
from app.infrastructure.database.repositories.project import ProjectRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class NavigationUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._navigation: NavigationRepository | None = None
        self._pages: PageRepository | None = None
        self._projects: ProjectRepository | None = None
        self._posts: PostRepository | None = None
        self._categories: CategoryRepository | None = None
        self._audit_logs: AuditLogRepository | None = None

    @property
    def navigation(self) -> NavigationRepository:
        if self._navigation is None:
            self._navigation = NavigationRepository(session=self.session)
        return self._navigation

    @property
    def pages(self) -> PageRepository:
        if self._pages is None:
            self._pages = PageRepository(session=self.session)
        return self._pages

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
