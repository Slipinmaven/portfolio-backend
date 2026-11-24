from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.enums import PostKind, PostStatus
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.models.post_resource import PostResource
from app.infrastructure.database.repositories.base import BaseRepository


class PostRepository(BaseRepository[Post, UUID]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Post)

    async def get_by_ids(self, post_ids: list[UUID]) -> list[Post]:
        if not post_ids:
            return []
        result = await self.session.scalars(
            select(Post).where(Post.id.in_(post_ids))
        )
        return list(result.all())

    async def get_published_by_ids(self, post_ids: list[UUID]) -> list[Post]:
        if not post_ids:
            return []
        result = await self.session.scalars(
            select(Post).where(
                Post.id.in_(post_ids),
                Post.status == PostStatus.PUBLISHED,
            )
        )
        return list(result.all())

    async def get_by_slug(self, kind: PostKind, slug: str) -> Post | None:
        query = select(Post).where(Post.kind == kind, Post.slug == slug)
        return await self.session.scalar(query)

    async def get_with_categories_by_id(self, post_id: UUID) -> Post | None:
        query = (
            select(Post)
            .options(
                selectinload(Post.categories),
                selectinload(Post.projects),
                selectinload(Post.resource_associations).selectinload(
                    PostResource.resource
                ),
                selectinload(Post.media_associations)
                .selectinload(PostMedia.media)
                .selectinload(Media.links),
            )
            .where(Post.id == post_id)
        )
        return await self.session.scalar(query)

    async def get_published_by_slug(
        self,
        kind: PostKind,
        slug: str,
    ) -> Post | None:
        query = (
            select(Post)
            .options(
                selectinload(Post.categories),
                selectinload(Post.projects),
                selectinload(Post.resource_associations).selectinload(
                    PostResource.resource
                ),
                selectinload(Post.media_associations)
                .selectinload(PostMedia.media)
                .selectinload(Media.links),
            )
            .where(
                Post.kind == kind,
                Post.slug == slug,
                Post.status == PostStatus.PUBLISHED,
            )
        )
        return await self.session.scalar(query)

    async def list_posts(
        self,
        *,
        offset: int,
        limit: int,
        kind: PostKind | None = None,
        status: PostStatus | None = None,
        published_only: bool = False,
        category_id: UUID | None = None,
    ) -> tuple[list[Post], int]:
        filters = []
        if kind is not None:
            filters.append(Post.kind == kind)
        if published_only:
            filters.append(Post.status == PostStatus.PUBLISHED)
        elif status is not None:
            filters.append(Post.status == status)
        if category_id is not None:
            filters.append(
                Post.categories.any(
                    and_(
                        Category.id == category_id,
                        Category.is_active.is_(True),
                    )
                )
            )

        query = (
            select(Post)
            .options(
                selectinload(Post.categories),
                selectinload(Post.projects),
                selectinload(Post.resource_associations).selectinload(
                    PostResource.resource
                ),
                selectinload(Post.media_associations)
                .selectinload(PostMedia.media)
                .selectinload(Media.links),
            )
            .where(*filters)
            .order_by(
                Post.published_at.desc().nullslast(),
                Post.updated_at.desc(),
                Post.id,
            )
            .offset(offset)
            .limit(limit)
        )
        posts = list((await self.session.scalars(query)).all())
        total_query = select(func.count()).select_from(Post).where(*filters)
        total = await self.session.scalar(total_query)
        return posts, total or 0
