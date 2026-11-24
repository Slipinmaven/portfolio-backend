from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.category import CategoryRepository
from app.infrastructure.database.repositories.tag import TagRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class CatalogUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._categories: CategoryRepository | None = None
        self._tags: TagRepository | None = None
        self._audit_logs: AuditLogRepository | None = None

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
