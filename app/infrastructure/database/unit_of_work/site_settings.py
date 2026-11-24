from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.media import MediaRepository
from app.infrastructure.database.repositories.site_settings import (
    SiteLinkRepository,
    SiteSettingsRepository,
)
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class SiteSettingsUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._settings: SiteSettingsRepository | None = None
        self._links: SiteLinkRepository | None = None
        self._media: MediaRepository | None = None
        self._audit_logs: AuditLogRepository | None = None

    @property
    def settings(self) -> SiteSettingsRepository:
        if self._settings is None:
            self._settings = SiteSettingsRepository(session=self.session)
        return self._settings

    @property
    def links(self) -> SiteLinkRepository:
        if self._links is None:
            self._links = SiteLinkRepository(session=self.session)
        return self._links

    @property
    def media(self) -> MediaRepository:
        if self._media is None:
            self._media = MediaRepository(session=self.session)
        return self._media

    @property
    def audit_logs(self) -> AuditLogRepository:
        if self._audit_logs is None:
            self._audit_logs = AuditLogRepository(session=self.session)
        return self._audit_logs
