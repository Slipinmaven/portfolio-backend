import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.projects.dto import (
    ProjectCreateDTO,
    ProjectListFilters,
    ProjectUpdateDTO,
)
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import (
    DevelopmentStatus,
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
    UserRole,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.models.tag import Tag
from app.infrastructure.database.models.user import User
from app.main import app
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.services import get_project_service


class ProjectRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    @staticmethod
    def _project(category_ids: list, tag_ids: list) -> Project:
        now = datetime.now(timezone.utc)
        project = Project(
            id=uuid4(),
            title="Demo",
            slug="demo",
            short_description="Demo project",
            development_status=DevelopmentStatus.IN_PROGRESS,
            display_order=0,
            status=ProjectStatus.DRAFT,
            is_featured=False,
            created_at=now,
            updated_at=now,
        )
        project.categories = [
            Category(
                id=category_id,
                name=f"Category {index}",
                slug=f"category-{index}",
                display_order=index,
                is_active=True,
            )
            for index, category_id in enumerate(category_ids)
        ]
        project.tags = [
            Tag(id=tag_id, name=f"Tag {index}", slug=f"tag-{index}", is_active=True)
            for index, tag_id in enumerate(tag_ids)
        ]
        return project

    def test_editor_can_create_project_and_receives_association_ids(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        category_id = uuid4()
        tag_id = uuid4()
        project = self._project([category_id], [tag_id])
        captured: dict[str, object] = {}

        class FakeProjectService:
            async def create_project(
                self,
                data: ProjectCreateDTO,
                *,
                actor_id,
            ) -> Project:
                captured["data"] = data
                captured["actor_id"] = actor_id
                return project

        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                json={
                    "title": "Demo",
                    "slug": "demo",
                    "short_description": "Demo project",
                    "development_status": "IN_PROGRESS",
                    "display_order": 0,
                    "category_ids": [str(category_id)],
                    "tag_ids": [str(tag_id)],
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], str(project.id))
        self.assertEqual(response.json()["category_ids"], [str(category_id)])
        self.assertEqual(response.json()["tag_ids"], [str(tag_id)])
        data = captured["data"]
        self.assertIsInstance(data, ProjectCreateDTO)
        self.assertEqual(data.category_ids, (category_id,))
        self.assertEqual(data.tag_ids, (tag_id,))
        self.assertEqual(captured["actor_id"], editor.id)

    def test_project_creation_requires_authentication(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                json={
                    "title": "Demo",
                    "slug": "demo",
                    "short_description": "Demo project",
                    "development_status": "IN_PROGRESS",
                    "display_order": 0,
                },
            )

        self.assertEqual(response.status_code, 401)

    def test_public_project_list_always_filters_to_published(self) -> None:
        captured: dict[str, ProjectListFilters] = {}

        class FakeProjectService:
            async def list_projects(
                self,
                filters: ProjectListFilters,
            ) -> tuple[list[Project], int]:
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.get("/api/v1/projects?status=DRAFT&limit=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["filters"].status, ProjectStatus.PUBLISHED)
        self.assertEqual(captured["filters"].limit, 5)
        self.assertTrue(captured["filters"].active_catalog_only)

    def test_public_project_list_includes_cover_metadata(self) -> None:
        project = self._project([], [])
        project_without_cover = self._project([], [])
        project_without_cover.slug = "project-without-cover"
        project.status = ProjectStatus.PUBLISHED
        project_without_cover.status = ProjectStatus.PUBLISHED
        project.published_at = datetime.now(timezone.utc)
        project_without_cover.published_at = project.published_at
        media = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            original_filename="cover.png",
            mime_type="image/png",
            storage_key="cover.png",
            size_bytes=1,
            checksum_sha256="0" * 64,
            title="Dashboard",
            alt_text="Analytics dashboard",
            width=1600,
            height=1065,
        )
        association = ProjectMedia(
            project_id=project.id,
            media_id=media.id,
            role=ProjectMediaRole.COVER,
            media=media,
        )

        class FakeProjectService:
            async def list_projects(
                self,
                filters: ProjectListFilters,
            ) -> tuple[list[Project], int]:
                return [project, project_without_cover], 2

            async def get_project_covers(
                self,
                project_ids: list[UUID],
            ) -> dict[UUID, ProjectMedia]:
                requested_ids = set(project_ids)
                return (
                    {project.id: association}
                    if project.id in requested_ids
                    else {}
                )

        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.get("/api/v1/projects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["projects"][0]["cover_media"],
            {
                "media_id": str(media.id),
                "title": "Dashboard",
                "alt_text": "Analytics dashboard",
                "file_url": f"/api/v1/media/{media.id}/content",
            },
        )
        self.assertIsNone(response.json()["projects"][1]["cover_media"])

    def test_project_management_list_requires_editor_or_admin(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/v1/projects/admin")

        self.assertEqual(response.status_code, 401)

    def test_editor_can_filter_management_list_by_status(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        captured: dict[str, ProjectListFilters] = {}

        class FakeProjectService:
            async def list_projects(
                self,
                filters: ProjectListFilters,
            ) -> tuple[list[Project], int]:
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.get("/api/v1/projects/admin?status=DRAFT&limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["filters"].status, ProjectStatus.DRAFT)
        self.assertEqual(captured["filters"].limit, 10)

    def test_public_project_detail_returns_published_project_by_slug(self) -> None:
        active_tag_id = uuid4()
        inactive_tag_id = uuid4()
        project = self._project([], [active_tag_id, inactive_tag_id])
        project.tags[1].is_active = False
        project.status = ProjectStatus.PUBLISHED
        project.published_at = datetime.now(timezone.utc)
        image_id = uuid4()
        video_id = uuid4()
        document_id = uuid4()
        media_items = [
            Media(
                id=image_id,
                kind=MediaKind.IMAGE,
                storage_key="projects/diagram.png",
                original_filename="diagram.png",
                mime_type="image/png",
                size_bytes=100,
                checksum_sha256="a" * 64,
                title="Diagram",
                alt_text="System diagram",
            ),
            Media(
                id=video_id,
                kind=MediaKind.VIDEO,
                storage_key="projects/walkthrough.mp4",
                original_filename="walkthrough.mp4",
                mime_type="video/mp4",
                size_bytes=100,
                checksum_sha256="b" * 64,
                title="Walkthrough",
            ),
            Media(
                id=document_id,
                kind=MediaKind.DOCUMENT,
                storage_key="projects/report.pdf",
                original_filename="report.pdf",
                mime_type="application/pdf",
                size_bytes=100,
                checksum_sha256="c" * 64,
                title="Report",
            ),
        ]
        project.media_associations = [
            ProjectMedia(
                project_id=project.id,
                media_id=item.id,
                role=ProjectMediaRole.INLINE,
                display_order=index,
                media=item,
            )
            for index, item in enumerate(media_items)
        ]
        project.overview = (
            "## Live overview\n<script>alert(1)</script>\n\n"
            f"![System diagram](media:{image_id})\n\n"
            f'![Walkthrough](media:{video_id} "media-video")\n\n'
            f"[Download the report](media:{document_id})"
        )
        captured: dict[str, str] = {}

        class FakeProjectService:
            async def get_published_project(self, slug: str) -> Project:
                captured["slug"] = slug
                return project

        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.get("/api/v1/projects/demo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "demo")
        overview_html = response.json()["overview_html"]
        self.assertIn("<h2>Live overview</h2>", overview_html)
        self.assertNotIn("<script>", overview_html)
        self.assertIn(
            f'<img src="/api/v1/media/{image_id}/content" alt="System diagram"',
            overview_html,
        )
        self.assertIn(
            f'src="/api/v1/media/{video_id}/content"',
            overview_html,
        )
        self.assertIn(
            f'<a href="/api/v1/media/{document_id}/content" download="">'
            "Download the report</a>",
            overview_html,
        )
        self.assertEqual(response.json()["tag_ids"], [str(active_tag_id)])
        self.assertEqual(
            response.json()["tags"],
            [{"id": str(active_tag_id), "name": "Tag 0", "slug": "tag-0"}],
        )
        self.assertEqual(captured["slug"], "demo")

    def test_editor_can_patch_project(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        project = self._project([], [])
        captured: dict[str, object] = {}

        class FakeProjectService:
            async def update_project(self, project_id, data, *, actor_id) -> Project:
                captured["project_id"] = project_id
                captured["data"] = data
                captured["actor_id"] = actor_id
                return project

        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/projects/admin/{project.id}",
                json={"title": "Updated", "overview": None, "tag_ids": []},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["project_id"], project.id)
        self.assertEqual(captured["actor_id"], editor.id)
        data = captured["data"]
        self.assertIsInstance(data, ProjectUpdateDTO)
        self.assertEqual(data.title, "Updated")
        self.assertIsNone(data.overview)
        self.assertEqual(data.tag_ids, ())
        self.assertEqual(data.fields_set, frozenset({"title", "overview", "tag_ids"}))

    def test_project_management_detail_requires_authentication(self) -> None:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/projects/admin/{uuid4()}")

        self.assertEqual(response.status_code, 401)

    def test_user_without_editor_role_cannot_create_project(self) -> None:
        user = User(
            id=uuid4(),
            email="viewer@example.com",
            password_hash="hashed",
            first_name="Viewer",
            last_name="User",
            role="viewer",
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                json={
                    "title": "Demo",
                    "slug": "demo",
                    "short_description": "Demo project",
                    "development_status": "IN_PROGRESS",
                    "display_order": 0,
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_invalid_project_body_is_rejected(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: editor

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                json={
                    "title": "Demo",
                    "slug": "Not Valid",
                    "short_description": "Demo project",
                    "development_status": "IN_PROGRESS",
                    "display_order": 0,
                },
            )

        self.assertEqual(response.status_code, 422)

    def test_service_conflicts_and_missing_associations_are_mapped(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )

        class FakeProjectService:
            async def create_project(self, data: ProjectCreateDTO, *, actor_id):
                raise ConflictError("A project with this slug already exists.")

        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_project_service] = lambda: FakeProjectService()

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                json={
                    "title": "Demo",
                    "slug": "demo",
                    "short_description": "Demo project",
                    "development_status": "IN_PROGRESS",
                    "display_order": 0,
                },
            )

        self.assertEqual(response.status_code, 409)

        class MissingAssociationService:
            async def create_project(self, data: ProjectCreateDTO, *, actor_id):
                raise ResourceNotFoundError("One or more selected tags do not exist.")

        app.dependency_overrides[get_project_service] = (
            lambda: MissingAssociationService()
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/projects",
                json={
                    "title": "Demo",
                    "slug": "demo",
                    "short_description": "Demo project",
                    "development_status": "IN_PROGRESS",
                    "display_order": 0,
                },
            )
        self.assertEqual(response.status_code, 404)
