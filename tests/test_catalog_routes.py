import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.application.categories.dto import CategoryListFilters
from app.application.errors import ResourceNotFoundError
from app.application.tags.dto import TagListFilters
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.main import app
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.services import (
    get_category_service,
    get_tag_service,
)


class CatalogRouteVisibilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_public_categories_are_always_filtered_to_active(self) -> None:
        captured: dict[str, CategoryListFilters] = {}

        class FakeCategoryService:
            async def list_categories(
                self,
                filters: CategoryListFilters,
            ) -> tuple[list, int]:
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_category_service] = (
            lambda: FakeCategoryService()
        )

        with TestClient(app) as client:
            response = client.get("/api/v1/categories?is_active=false")

        self.assertEqual(response.status_code, 200)
        self.assertIs(captured["filters"].is_active, True)

    def test_admin_categories_can_filter_inactive_records(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        captured: dict[str, CategoryListFilters] = {}

        class FakeCategoryService:
            async def list_categories(
                self,
                filters: CategoryListFilters,
            ) -> tuple[list, int]:
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_category_service] = (
            lambda: FakeCategoryService()
        )

        with TestClient(app) as client:
            response = client.get("/api/v1/categories/admin?is_active=false")

        self.assertEqual(response.status_code, 200)
        self.assertIs(captured["filters"].is_active, False)

    def test_category_management_list_requires_admin(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/v1/categories/admin")

        self.assertEqual(response.status_code, 401)

    def test_admin_can_move_category_with_direction_command(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        category = Category(
            id=uuid4(),
            parent_id=None,
            name="Backend",
            slug="backend",
            description=None,
            display_order=0,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        captured: dict[str, object] = {}

        class FakeCategoryService:
            async def move_category(self, category_id, direction, *, actor_id):
                captured["category_id"] = category_id
                captured["direction"] = direction
                captured["actor_id"] = actor_id
                return category

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_category_service] = (
            lambda: FakeCategoryService()
        )

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/categories/{category.id}/move",
                json={"direction": "up"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["category_id"], category.id)
        self.assertEqual(captured["direction"], "up")
        self.assertEqual(captured["actor_id"], admin.id)
        self.assertEqual(response.json()["display_order"], 0)

    def test_editor_cannot_move_categories(self) -> None:
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
                f"/api/v1/categories/{uuid4()}/move",
                json={"direction": "up"},
            )

        self.assertEqual(response.status_code, 403)

    def test_public_tags_are_always_filtered_to_active(self) -> None:
        captured: dict[str, TagListFilters] = {}

        class FakeTagService:
            async def list_tags(self, filters: TagListFilters) -> tuple[list, int]:
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_tag_service] = lambda: FakeTagService()

        with TestClient(app) as client:
            response = client.get("/api/v1/tags?is_active=false")

        self.assertEqual(response.status_code, 200)
        self.assertIs(captured["filters"].is_active, True)

    def test_admin_tags_can_list_all_states(self) -> None:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            password_hash="hashed",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        captured: dict[str, TagListFilters] = {}

        class FakeTagService:
            async def list_tags(self, filters: TagListFilters) -> tuple[list, int]:
                captured["filters"] = filters
                return [], 0

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_tag_service] = lambda: FakeTagService()

        with TestClient(app) as client:
            response = client.get("/api/v1/tags/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(captured["filters"].is_active)

    def test_inactive_tags_are_not_found_on_public_detail_route(self) -> None:
        class FakeTagService:
            async def get_active_tag(self, tag_id):
                raise ResourceNotFoundError("Tag not found.")

        app.dependency_overrides[get_tag_service] = lambda: FakeTagService()

        with TestClient(app) as client:
            response = client.get(f"/api/v1/tags/{uuid4()}")

        self.assertEqual(response.status_code, 404)
