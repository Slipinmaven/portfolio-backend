from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.enums import PostStatus
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.repositories.base import BaseRepository


class PostMediaRepository(BaseRepository[PostMedia, tuple[UUID, UUID, str]]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=PostMedia)

    async def has_published_usage(self, media_id: UUID) -> bool:
        query = select(
            exists().where(
                PostMedia.media_id == media_id,
                PostMedia.post_id == Post.id,
                Post.status == PostStatus.PUBLISHED,
            )
        )
        return bool(await self.session.scalar(query))

    async def list_by_media(self, media_id: UUID) -> list[PostMedia]:
        query = (
            select(PostMedia)
            .options(
                selectinload(PostMedia.post),
                selectinload(PostMedia.media).selectinload(Media.links),
            )
            .where(PostMedia.media_id == media_id)
            .order_by(PostMedia.post_id, PostMedia.role, PostMedia.display_order)
        )
        result = await self.session.scalars(query)
        return list(result.all())
