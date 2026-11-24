import unittest

from pydantic import ValidationError

from app.presentation.schemas.categories import (
    CreateCategoryRequest,
    MoveCategoryRequest,
    UpdateCategoryRequest,
)
from app.presentation.schemas.tags import CreateTagRequest, UpdateTagRequest
from app.presentation.schemas.projects import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
)
from app.infrastructure.database.models.enums import DevelopmentStatus


class CatalogSchemaTests(unittest.TestCase):
    def test_create_category_validates_slug_and_order(self) -> None:
        category = CreateCategoryRequest(
            name="Backend",
            slug="backend",
            display_order=0,
        )

        self.assertEqual(category.name, "Backend")
        self.assertFalse(category.is_active)
        self.assertEqual(category.display_order, 0)
        with self.assertRaises(ValidationError):
            CreateCategoryRequest(
                name="Backend",
                slug="Backend",
                display_order=-1,
            )

    def test_category_patch_preserves_explicit_null_parent(self) -> None:
        request = UpdateCategoryRequest(parent_id=None)

        self.assertIn("parent_id", request.model_fields_set)
        self.assertIsNone(request.parent_id)
        with self.assertRaises(ValidationError):
            UpdateCategoryRequest(name=None)
        with self.assertRaises(ValidationError):
            UpdateCategoryRequest()

    def test_category_move_accepts_only_supported_directions(self) -> None:
        self.assertEqual(MoveCategoryRequest(direction="up").direction, "up")
        with self.assertRaises(ValidationError):
            MoveCategoryRequest(direction="first")

    def test_create_tag_and_patch_validation(self) -> None:
        tag = CreateTagRequest(name="Python", slug="python")
        self.assertFalse(tag.is_active)

        request = UpdateTagRequest(description=None)
        self.assertIn("description", request.model_fields_set)
        with self.assertRaises(ValidationError):
            UpdateTagRequest(is_active=None)
        with self.assertRaises(ValidationError):
            CreateTagRequest(name="Python", slug="bad slug")

    def test_project_creation_rejects_negative_display_order(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectCreateRequest(
                title="Example",
                slug="example",
                short_description="Example project",
                development_status=DevelopmentStatus.PLANNING,
                display_order=-1,
            )

    def test_project_patch_preserves_nullable_fields_and_rejects_empty_patch(self) -> None:
        request = ProjectUpdateRequest(overview=None)

        self.assertIn("overview", request.model_fields_set)
        self.assertIsNone(request.overview)
        with self.assertRaises(ValidationError):
            ProjectUpdateRequest()
        with self.assertRaises(ValidationError):
            ProjectUpdateRequest(title=None)
        with self.assertRaises(ValidationError):
            ProjectUpdateRequest(category_ids=None)
