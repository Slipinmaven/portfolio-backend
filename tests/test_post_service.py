import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.application.errors import ConflictError
from app.application.posts.dto import PostCreateDTO, PostUpdateDTO
from app.application.posts.markdown import render_markdown
from app.application.posts.service import PostService
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import (
    MediaKind,
    PostKind,
    PostMediaRole,
    PostStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.unit_of_work.posts import PostsUnitOfWork


class PostServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.uow = MagicMock(spec=PostsUnitOfWork)
        self.uow.posts = MagicMock()
        self.uow.categories = MagicMock()
        self.uow.audit_logs = MagicMock()
        self.uow.media = MagicMock()
        self.uow.projects = MagicMock()
        self.uow.resources = MagicMock()
        self.uow.posts.get_by_slug = AsyncMock(return_value=None)
        self.uow.posts.get_with_categories_by_id = AsyncMock()
        self.uow.categories.get_active_by_ids = AsyncMock(return_value=[])
        self.uow.media.get_by_ids = AsyncMock(return_value=[])
        self.uow.projects.get_by_ids = AsyncMock(return_value=[])
        self.uow.resources.get_by_ids = AsyncMock(return_value=[])
        self.uow.audit_logs.create = AsyncMock()
        self.uow.commit = AsyncMock()
        self.uow.rollback = AsyncMock()
        self.uow.posts.create = AsyncMock(
            side_effect=lambda post: setattr(post, "id", uuid4())
        )
        self.service = PostService(self.uow)
        self.actor_id = uuid4()

    def make_post(
        self,
        *,
        kind: PostKind = PostKind.ARTICLE,
        status: PostStatus = PostStatus.DRAFT,
        categories: list[Category] | None = None,
        summary: str | None = "A summary",
    ) -> Post:
        post = Post(
            id=uuid4(),
            kind=kind,
            title="A post",
            slug="a-post",
            summary=summary,
            body="## Body",
            status=status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        post.categories = categories or []
        return post

    async def test_create_post_saves_a_draft_and_audit_atomically(self) -> None:
        category = Category(
            id=uuid4(),
            name="Engineering",
            slug="engineering",
            is_active=True,
        )
        self.uow.categories.get_active_by_ids.return_value = [category]
        created: dict[object, Post] = {}

        async def persist(post: Post) -> None:
            post.id = uuid4()
            created[post.id] = post

        async def reload(post_id) -> Post | None:
            return created.get(post_id)

        self.uow.posts.create.side_effect = persist
        self.uow.posts.get_with_categories_by_id.side_effect = reload

        post = await self.service.create_post(
            PostCreateDTO(
                kind=PostKind.ARTICLE,
                title="  A post ",
                slug="a-post",
                category_ids=(category.id,),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(post.title, "A post")
        self.assertEqual(post.status, PostStatus.DRAFT)
        self.assertEqual(post.categories, [category])
        self.uow.audit_logs.create.assert_awaited_once()
        audit = self.uow.audit_logs.create.await_args.args[0]
        self.assertEqual(audit.action, "post.created")
        self.assertEqual(audit.user_id, self.actor_id)
        self.uow.commit.assert_awaited_once()
        self.assertEqual(
            self.uow.posts.get_with_categories_by_id.await_count,
            2,
        )

    async def test_update_tracks_inline_images_attachments_and_projects(self) -> None:
        image = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            alt_text="An illustrated dashboard",
        )
        document = Media(
            id=uuid4(),
            kind=MediaKind.DOCUMENT,
            original_filename="report.pdf",
        )
        project = Project(
            id=uuid4(),
            title="A project",
            slug="a-project",
            short_description="A project description",
            status="DRAFT",
        )
        post = self.make_post(kind=PostKind.NOTE)
        self.uow.posts.get_with_categories_by_id.return_value = post

        async def get_media_by_ids(media_ids):
            records = {image.id: image, document.id: document}
            return [records[media_id] for media_id in media_ids]

        self.uow.media.get_by_ids.side_effect = get_media_by_ids
        self.uow.projects.get_by_ids.return_value = [project]
        body = (
            f'![Dashboard \\] preview](media:{image.id} '
            '"media-layout:width=58;align=right")'
        )

        updated = await self.service.update_post(
            post.id,
            PostUpdateDTO(
                body=body,
                attachment_media_ids=(document.id,),
                project_ids=(project.id,),
                fields_set=frozenset(
                    {"body", "attachment_media_ids", "project_ids"}
                ),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(updated.projects, [project])
        self.assertEqual(updated.body, body)
        self.assertEqual(
            {(item.media_id, item.role) for item in updated.media_associations},
            {
                (image.id, PostMediaRole.INLINE),
                (document.id, PostMediaRole.ATTACHMENT),
            },
        )
        self.uow.commit.assert_awaited_once()
        self.assertEqual(
            self.uow.posts.get_with_categories_by_id.await_count,
            2,
        )

    async def test_publishing_requires_alt_text_for_inline_images(self) -> None:
        image = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            alt_text=None,
        )
        post = self.make_post(kind=PostKind.NOTE)
        post.body = f"![](media:{image.id})"
        post.media_associations = [
            PostMedia(
                media_id=image.id,
                media=image,
                role=PostMediaRole.INLINE,
            )
        ]
        self.uow.posts.get_with_categories_by_id.return_value = post

        with self.assertRaisesRegex(ConflictError, "alternative text"):
            await self.service.update_post(
                post.id,
                PostUpdateDTO(
                    status=PostStatus.PUBLISHED,
                    fields_set=frozenset({"status"}),
                ),
                actor_id=self.actor_id,
            )

        self.uow.commit.assert_not_awaited()

    async def test_publishing_article_requires_summary_and_category(self) -> None:
        post = self.make_post(summary=None)
        self.uow.posts.get_with_categories_by_id.return_value = post

        with self.assertRaisesRegex(ConflictError, "summary"):
            await self.service.update_post(
                post.id,
                PostUpdateDTO(
                    status=PostStatus.PUBLISHED,
                    fields_set=frozenset({"status"}),
                ),
                actor_id=self.actor_id,
            )

        self.uow.commit.assert_not_awaited()

    async def test_publishing_article_requires_a_category(self) -> None:
        post = self.make_post()
        self.uow.posts.get_with_categories_by_id.return_value = post

        with self.assertRaisesRegex(ConflictError, "category"):
            await self.service.update_post(
                post.id,
                PostUpdateDTO(
                    status=PostStatus.PUBLISHED,
                    fields_set=frozenset({"status"}),
                ),
                actor_id=self.actor_id,
            )

        self.uow.commit.assert_not_awaited()

    async def test_note_can_publish_without_summary_or_category(self) -> None:
        post = self.make_post(
            kind=PostKind.NOTE,
            categories=[],
        )
        post.summary = None
        self.uow.posts.get_with_categories_by_id.return_value = post

        updated = await self.service.update_post(
            post.id,
            PostUpdateDTO(
                status=PostStatus.PUBLISHED,
                fields_set=frozenset({"status"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(updated.status, PostStatus.PUBLISHED)
        self.assertIsNotNone(updated.published_at)
        self.uow.commit.assert_awaited_once()

    async def test_unpublishing_preserves_first_publication_date(self) -> None:
        published_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
        post = self.make_post(status=PostStatus.PUBLISHED)
        post.published_at = published_at
        self.uow.posts.get_with_categories_by_id.return_value = post

        updated = await self.service.update_post(
            post.id,
            PostUpdateDTO(
                status=PostStatus.DRAFT,
                fields_set=frozenset({"status"}),
            ),
            actor_id=self.actor_id,
        )

        self.assertEqual(updated.status, PostStatus.DRAFT)
        self.assertEqual(updated.published_at, published_at)
        self.assertIsNone(updated.archived_at)

    async def test_slug_is_locked_after_first_publication(self) -> None:
        post = self.make_post()
        post.published_at = datetime.now(timezone.utc)
        self.uow.posts.get_with_categories_by_id.return_value = post

        with self.assertRaisesRegex(ConflictError, "cannot be changed"):
            await self.service.update_post(
                post.id,
                PostUpdateDTO(
                    slug="new-slug",
                    fields_set=frozenset({"slug"}),
                ),
                actor_id=self.actor_id,
            )

        self.uow.commit.assert_not_awaited()

    def test_markdown_preview_escapes_raw_html_and_rejects_javascript_links(self) -> None:
        rendered = render_markdown(
            '<script>alert("x")</script>\n\n[unsafe](javascript:alert(1))'
        )

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn('href="javascript:', rendered)

    def test_markdown_preview_renders_escaped_bracket_in_media_alt_text(self) -> None:
        media_id = uuid4()
        rendered = render_markdown(
            f"![Dashboard \\] preview](media:{media_id})",
            media_url_resolver=lambda resolved_id: (
                f"/api/v1/media/{resolved_id}/content"
            ),
        )

        self.assertIn(
            f'<img src="/api/v1/media/{media_id}/content" alt="Dashboard ] preview" />',
            rendered,
        )

    def test_markdown_preview_renders_saved_image_size_and_alignment(self) -> None:
        media_id = uuid4()
        rendered = render_markdown(
            f'![Dashboard](media:{media_id} '
            '"media-layout:width=58;align=right")',
            media_url_resolver=lambda resolved_id: (
                f"/api/v1/media/{resolved_id}/content"
            ),
        )

        self.assertIn(
            f'src="/api/v1/media/{media_id}/content"',
            rendered,
        )
        self.assertIn(
            'style="width: 58%; display: block; margin-left: auto; '
            'margin-right: 0; height: auto;"',
            rendered,
        )
        self.assertNotIn("media-layout", rendered)

    def test_markdown_preview_ignores_out_of_range_image_widths(self) -> None:
        rendered = render_markdown(
            '![Dashboard](https://example.com/image.jpg '
            '"media-layout:width=101;align=center")'
        )

        self.assertNotIn("style=", rendered)
        self.assertNotIn("media-layout", rendered)


if __name__ == "__main__":
    unittest.main()
