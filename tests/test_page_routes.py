import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.application.pages.dto import PageCreateDTO
from app.application.pages.blocks import MarkdownBlock
from app.application.pages.dto import PublicPageData
from app.infrastructure.database.models.enums import (
    PageRevisionState,
    PageStatus,
    UserRole,
)
from app.infrastructure.database.models.page import Page
from app.infrastructure.database.models.page_revision import PageRevision
from app.infrastructure.database.models.user import User
from app.main import app
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.services import get_page_service


class PageRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

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

    def test_page_management_list_requires_authentication(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/v1/pages/admin")

        self.assertEqual(response.status_code, 401)

    def test_editor_can_create_a_page_with_a_draft_revision(self) -> None:
        editor = self._editor()
        page_id = uuid4()
        revision_id = uuid4()
        now = datetime.now(timezone.utc)
        page = Page(
            id=page_id,
            slug="uses",
            system_key=None,
            status=PageStatus.DRAFT,
            published_at=None,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )
        page.revisions = [
            PageRevision(
                id=revision_id,
                page_id=page_id,
                revision_number=1,
                state=PageRevisionState.DRAFT,
                title="Uses",
                summary=None,
                sections=[],
                schema_version=1,
                change_note=None,
                published_at=None,
                superseded_at=None,
                created_at=now,
                updated_at=now,
            )
        ]
        captured: dict[str, object] = {}

        class FakePageService:
            async def create_page(self, data: PageCreateDTO, *, actor_id):
                captured["data"] = data
                captured["actor_id"] = actor_id
                return page

        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_page_service] = lambda: FakePageService()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/pages/admin",
                json={"slug": "uses", "title": "Uses"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "DRAFT")
        self.assertEqual(response.json()["draft_revision"]["title"], "Uses")
        self.assertEqual(captured["actor_id"], editor.id)
        self.assertIsInstance(captured["data"], PageCreateDTO)

    def test_editor_cannot_submit_an_unsupported_block(self) -> None:
        app.dependency_overrides[get_current_user] = lambda: self._editor()
        app.dependency_overrides[get_page_service] = lambda: object()

        with TestClient(app) as client:
            invalid = client.put(
                f"/api/v1/pages/admin/{uuid4()}/draft",
                json={
                    "slug": "uses",
                    "title": "Uses",
                    "summary": None,
                    "sections": [{"id": str(uuid4()), "type": "UNKNOWN"}],
                },
            )

        self.assertEqual(invalid.status_code, 422)

    def test_public_page_route_returns_published_rendered_content(self) -> None:
        markdown = MarkdownBlock(
            id=uuid4(),
            type="MARKDOWN",
            body="## Public content",
        )
        page_data = PublicPageData(
            slug="about",
            title="About",
            summary="A public summary",
            published_at=datetime.now(timezone.utc),
            sections=[markdown],
            images=[],
            projects=[],
            pages=[],
            posts=[],
        )

        class FakePageService:
            async def get_public_page_by_slug(self, slug: str) -> PublicPageData:
                self_slug = slug
                if self_slug != "about":
                    raise AssertionError("Unexpected page slug.")
                return page_data

        app.dependency_overrides[get_page_service] = lambda: FakePageService()

        with TestClient(app) as client:
            response = client.get("/api/v1/pages/about")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["title"], "About")
        self.assertIsNone(body["system_key"])
        self.assertEqual(body["sections"][0]["body"], "## Public content")
        self.assertIn(
            "<h2>Public content</h2>",
            body["rendered_markdown"][str(markdown.id)],
        )
