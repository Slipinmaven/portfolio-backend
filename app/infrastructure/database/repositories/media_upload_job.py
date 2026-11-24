from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.media_upload_job import MediaUploadJob
from app.infrastructure.database.repositories.base import BaseRepository


class MediaUploadJobRepository(BaseRepository[MediaUploadJob, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=MediaUploadJob)
