from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.enums import MediaKind
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.models.page_media import PageMedia
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.repositories.base import BaseRepository


class MediaRepository(BaseRepository[Media, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Media)

    async def get_by_storage_key(self, storage_key: str) -> Media | None:
        query = select(Media).where(Media.storage_key == storage_key)
        return await self.session.scalar(query)

    async def get_with_links(self, media_id: UUID) -> Media | None:
        query = (
            select(Media)
            .options(selectinload(Media.links))
            .where(Media.id == media_id)
        )
        return await self.session.scalar(query)

    async def get_by_ids(self, media_ids: list[UUID]) -> list[Media]:
        if not media_ids:
            return []
        query = (
            select(Media)
            .options(selectinload(Media.links))
            .where(Media.id.in_(media_ids))
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_by_checksum(self, checksum_sha256: str) -> list[Media]:
        query = (
            select(Media)
            .where(Media.checksum_sha256 == checksum_sha256)
            .order_by(Media.created_at.desc(), Media.id)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def get_storage_usage_by_kind(
        self,
    ) -> list[tuple[MediaKind, int, int]]:
        query = (
            select(
                Media.kind,
                func.count(Media.id),
                func.coalesce(func.sum(Media.size_bytes), 0),
            )
            .group_by(Media.kind)
            .order_by(Media.kind)
        )
        result = await self.session.execute(query)
        return [
            (kind, int(item_count), int(size_bytes))
            for kind, item_count, size_bytes in result.all()
        ]

    async def list_video_storage_keys(self) -> list[str]:
        query = select(Media.storage_key).where(Media.kind == MediaKind.VIDEO)
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_largest_media(self, *, limit: int) -> list[Media]:
        query = (
            select(Media)
            .order_by(Media.size_bytes.desc(), Media.created_at.desc(), Media.id)
            .limit(limit)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def list_media(
        self,
        *,
        offset: int,
        limit: int,
        kind: MediaKind | None = None,
        query_text: str | None = None,
        unused_only: bool = False,
    ) -> tuple[list[Media], int]:
        filters = []
        if kind is not None:
            filters.append(Media.kind == kind)
        if query_text:
            search = f"%{query_text.strip()}%"
            filters.append(
                or_(
                    Media.original_filename.ilike(search),
                    Media.title.ilike(search),
                )
            )
        if unused_only:
            filters.append(
                ~or_(
                    exists().where(ProjectMedia.media_id == Media.id),
                    exists().where(PostMedia.media_id == Media.id),
                    exists().where(PageMedia.media_id == Media.id),
                    exists().where(
                        or_(
                            SiteSettings.logo_media_id == Media.id,
                            SiteSettings.favicon_media_id == Media.id,
                            SiteSettings.default_social_image_media_id == Media.id,
                            SiteSettings.profile_image_media_id == Media.id,
                        )
                    ),
                )
            )

        order_by = (
            (Media.size_bytes.desc(), Media.created_at.desc(), Media.id)
            if unused_only
            else (Media.created_at.desc(), Media.id)
        )
        query = (
            select(Media)
            .options(selectinload(Media.links))
            .where(*filters)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
        media = list((await self.session.scalars(query)).all())
        total_query = select(func.count()).select_from(Media).where(*filters)
        total = await self.session.scalar(total_query)
        return media, total or 0
