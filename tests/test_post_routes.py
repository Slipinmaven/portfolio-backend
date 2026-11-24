import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.application.errors import ResourceNotFoundError
from app.application.posts.dto import PostCreateDTO, PostListFilters
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import (
    DevelopmentStatus,
    MediaKind,
    PostKind,
    PostMediaRole,
    PostStatus,
    ProjectStatus,
    UserRole,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.post import Post
from app.infrastructure.database.models.post_media import PostMedia
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.user import User
from app.main import app
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.services import get_post_service


class PostRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    @staticmethod
    def _post(
        *,
        kind: PostKind = PostKind.ARTICLE,
        status: PostStatus = PostStatus.DRAFT,
    ) -> Post:
        now = datetime.now(timezone.utc)
        post = Post(
            id=uuid4(),
            kind=kind,
            title="A post",
            slug="a-post",
            summary="A summary",
            body="## Hello",
            status=status,
            published_at=now if status == PostStatus.PUBLISHED else None,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )
        post.categories = [
            Category(
                id=uuid4(),
                name="Engineering",
                slug="engineering",
                is_active=True,
            )
        ]
        return post

    @staticmethod
    def _editor() -> User:
        return User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )

    def test_editor_can_create_a_draft_post(self) -> None:
        editor = self._editor()
        post = self._post()
        captured: dict[str, object] = {}

        class FakePostService:
            async def create_post(self, data: PostCreateDTO, *, actor_id):
                captured["data"] = data
                captured["actor_id"] = actor_id
                return post

        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_post_service] = lambda: FakePostService()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/posts",
                json={
                    "kind": "ARTICLE",
                    "title": "A post",
                    "slug": "a-post",
                    "body": "## Hello",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "DRAFT")
        self.assertEqual(captured["actor_id"], editor.id)
        self.assertIsInstance(captured["data"], PostCreateDTO)

    def test_management_list_requires_authentication(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/v1/posts/admin")

        self.assertEqual(response.status_code, 401)

    def test_public_list_filters_by_kind_and_published_status(self) -> None:
        captured: dict[str, PostListFilters] = {}

        class FakePostService:
            async def list_posts(self, filters: PostListFilters):
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_post_service] = lambda: FakePostService()

        with TestClient(app) as client:
            response = client.get("/api/v1/posts/NOTE?limit=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["filters"].kind, PostKind.NOTE)
        self.assertTrue(captured["filters"].published_only)
        self.assertEqual(captured["filters"].limit, 7)

    def test_public_detail_returns_rendered_published_post(self) -> None:
        post = self._post(status=PostStatus.PUBLISHED)
        captured: dict[str, object] = {}

        class FakePostService:
            async def get_published_post(self, kind, slug):
                captured["kind"] = kind
                captured["slug"] = slug
                return post

        app.dependency_overrides[get_post_service] = lambda: FakePostService()

        with TestClient(app) as client:
            response = client.get("/api/v1/posts/ARTICLE/a-post")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["body_html"], "<h2>Hello</h2>\n")
        self.assertEqual(captured["kind"], PostKind.ARTICLE)
        self.assertEqual(captured["slug"], "a-post")

    def test_public_detail_resolves_post_media_and_hides_draft_projects(self) -> None:
        post = self._post(status=PostStatus.PUBLISHED)
        image = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            storage_key="images/dashboard.webp",
            original_filename="dashboard.webp",
            mime_type="image/webp",
            size_bytes=1234,
            checksum_sha256="a" * 64,
        )
        document = Media(
            id=uuid4(),
            kind=MediaKind.DOCUMENT,
            storage_key="documents/report.pdf",
            original_filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=4567,
            checksum_sha256="b" * 64,
            title="Project report",
        )
        post.body = f"![Dashboard](media:{image.id})"
        post.media_associations = [
            PostMedia(
                post_id=post.id,
                media_id=image.id,
                media=image,
                role=PostMediaRole.INLINE,
            ),
            PostMedia(
                post_id=post.id,
                media_id=document.id,
                media=document,
                role=PostMediaRole.ATTACHMENT,
            ),
        ]
        published_project = Project(
            id=uuid4(),
            title="Published project",
            slug="published-project",
            short_description="A public project",
            status=ProjectStatus.PUBLISHED,
            development_status=DevelopmentStatus.COMPLETED,
            display_order=0,
            is_featured=False,
        )
        draft_project = Project(
            id=uuid4(),
            title="Draft project",
            slug="draft-project",
            short_description="A private project",
            status=ProjectStatus.DRAFT,
            development_status=DevelopmentStatus.PLANNING,
            display_order=1,
            is_featured=False,
        )
        post.projects = [published_project, draft_project]

        class FakePostService:
            async def get_published_post(self, kind, slug):
                return post

        app.dependency_overrides[get_post_service] = lambda: FakePostService()

        with TestClient(app) as client:
            response = client.get("/api/v1/posts/ARTICLE/a-post")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(
            f'src="/api/v1/media/{image.id}/content"',
            body["body_html"],
        )
        self.assertEqual(
            body["attachments"],
            [
                {
                    "media_id": str(document.id),
                    "title": "Project report",
                    "original_filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": 4567,
                    "file_url": f"/api/v1/media/{document.id}/content",
                }
            ],
        )
        self.assertEqual(
            [project["slug"] for project in body["related_projects"]],
            ["published-project"],
        )

    def test_public_detail_does_not_expose_drafts(self) -> None:
        class FakePostService:
            async def get_published_post(self, kind, slug):
                raise ResourceNotFoundError("Post not found.")

        app.dependency_overrides[get_post_service] = lambda: FakePostService()

        with TestClient(app) as client:
            response = client.get("/api/v1/posts/ARTICLE/a-post")

        self.assertEqual(response.status_code, 404)

    def test_markdown_preview_requires_editor_authentication(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/posts/admin/preview",
                json={"body": "# Preview"},
            )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
