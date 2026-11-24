from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.audit_logs import AuditLogRepository
from app.infrastructure.database.repositories.media import MediaRepository
from app.infrastructure.database.repositories.media_upload_job import (
    MediaUploadJobRepository,
)
from app.infrastructure.database.repositories.media_link import MediaLinkRepository
from app.infrastructure.database.repositories.page_media import PageMediaRepository
from app.infrastructure.database.repositories.project_media import (
    ProjectMediaRepository,
)
from app.infrastructure.database.repositories.post_media import PostMediaRepository
from app.infrastructure.database.repositories.site_settings import (
    SiteSettingsRepository,
)
from app.infrastructure.database.unit_of_work.base import BaseUnitOfWork


class MediaUnitOfWork(BaseUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session)
        self._media: MediaRepository | None = None
        self._media_upload_jobs: MediaUploadJobRepository | None = None
        self._media_links: MediaLinkRepository | None = None
        self._page_media: PageMediaRepository | None = None
        self._project_media: ProjectMediaRepository | None = None
        self._post_media: PostMediaRepository | None = None
        self._audit_logs: AuditLogRepository | None = None
        self._site_settings: SiteSettingsRepository | None = None

    @property
    def media(self) -> MediaRepository:
        if self._media is None:
            self._media = MediaRepository(session=self.session)
        return self._media

    @property
    def media_upload_jobs(self) -> MediaUploadJobRepository:
        if self._media_upload_jobs is None:
            self._media_upload_jobs = MediaUploadJobRepository(session=self.session)
        return self._media_upload_jobs

    @property
    def media_links(self) -> MediaLinkRepository:
        if self._media_links is None:
            self._media_links = MediaLinkRepository(session=self.session)
        return self._media_links

    @property
    def page_media(self) -> PageMediaRepository:
        if self._page_media is None:
            self._page_media = PageMediaRepository(session=self.session)
        return self._page_media

    @property
    def project_media(self) -> ProjectMediaRepository:
        if self._project_media is None:
            self._project_media = ProjectMediaRepository(session=self.session)
        return self._project_media

    @property
    def post_media(self) -> PostMediaRepository:
        if self._post_media is None:
            self._post_media = PostMediaRepository(session=self.session)
        return self._post_media

    @property
    def audit_logs(self) -> AuditLogRepository:
        if self._audit_logs is None:
            self._audit_logs = AuditLogRepository(session=self.session)
        return self._audit_logs

    @property
    def site_settings(self) -> SiteSettingsRepository:
        if self._site_settings is None:
            self._site_settings = SiteSettingsRepository(session=self.session)
        return self._site_settings
