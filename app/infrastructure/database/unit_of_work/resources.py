from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.resource import ResourceRepository
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class ResourcesUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._resources: ResourceRepository | None = None
        self._audit_logs: AuditLogRepository | None = None

    @property
    def resources(self) -> ResourceRepository:
        if self._resources is None:
            self._resources = ResourceRepository(session=self.session)
        return self._resources

    @property
    def audit_logs(self) -> AuditLogRepository:
        if self._audit_logs is None:
            self._audit_logs = AuditLogRepository(session=self.session)
        return self._audit_logs
