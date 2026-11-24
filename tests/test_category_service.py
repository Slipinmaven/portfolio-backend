import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.application.categories.dto import CreateCategoryData, UpdateCategoryData
from app.application.categories.service import CategoryService
from app.application.errors import ConflictError
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.unit_of_work.catalog import CatalogUnitOfWork


class CategoryServiceDepthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.uow = MagicMock(spec=CatalogUnitOfWork)
        self.uow.categories = MagicMock()
        self.uow.audit_logs = MagicMock()
        self.uow.categories.get_by_id = AsyncMock()
        self.uow.categories.list_siblings_for_update = AsyncMock()
        self.uow.categories.get_children = AsyncMock(return_value=[])
        self.uow.categories.create = AsyncMock()
        self.uow.audit_logs.create = AsyncMock()
        self.uow.commit = AsyncMock()
        self.uow.rollback = AsyncMock()
        self.service = CategoryService(self.uow)

    @staticmethod
    def category(parent_id=None) -> Category:
        return Category(
            id=uuid4(),
            parent_id=parent_id,
            name="Category",
            slug=f"category-{uuid4().hex}",
            display_order=0,
            is_active=False,
        )

    async def test_create_rejects_category_beyond_four_levels(self) -> None:
        root = self.category()
        second = self.category(root.id)
        third = self.category(second.id)
        fourth = self.category(third.id)
        self.uow.categories.get_by_id.side_effect = [fourth, third, second, root]

        with self.assertRaises(ConflictError):
            await self.service.create_category(
                CreateCategoryData(
                    name="Fifth",
                    slug="fifth",
                    parent_id=fourth.id,
                ),
                actor_id=uuid4(),
            )

        self.uow.categories.create.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_move_category_up_reorders_siblings_and_audits_atomically(
        self,
    ) -> None:
        first = self.category()
        moving = self.category()
        last = self.category()
        first.display_order = 4
        moving.display_order = 8
        last.display_order = 12
        self.uow.categories.get_by_id.return_value = moving
        self.uow.categories.list_siblings_for_update.return_value = [
            last,
            first,
            moving,
        ]

        result = await self.service.move_category(
            moving.id,
            "up",
            actor_id=uuid4(),
        )

        self.assertIs(result, moving)
        self.assertEqual(
            [first.display_order, moving.display_order, last.display_order],
            [1, 0, 2],
        )
        self.uow.audit_logs.create.assert_awaited_once()
        self.uow.commit.assert_awaited_once()
        self.uow.rollback.assert_not_awaited()

    async def test_move_category_at_boundary_is_a_no_op(self) -> None:
        first = self.category()
        first.display_order = 5
        self.uow.categories.get_by_id.return_value = first
        self.uow.categories.list_siblings_for_update.return_value = [first]

        result = await self.service.move_category(
            first.id,
            "up",
            actor_id=uuid4(),
        )

        self.assertIs(result, first)
        self.assertEqual(first.display_order, 5)
        self.uow.audit_logs.create.assert_not_awaited()
        self.uow.commit.assert_awaited_once()

    async def test_parent_move_accounts_for_descendant_depth(self) -> None:
        root = self.category()
        destination = self.category(root.id)
        moving = self.category()
        child = self.category(moving.id)
        grandchild = self.category(child.id)
        self.uow.categories.get_by_id.side_effect = [moving, destination, root]
        self.uow.categories.get_children.side_effect = [
            [child],
            [grandchild],
            [],
        ]

        with self.assertRaises(ConflictError):
            await self.service.update_category(
                moving.id,
                UpdateCategoryData(
                    name=None,
                    slug=None,
                    description=None,
                    parent_id=destination.id,
                    display_order=None,
                    is_active=None,
                    fields_set=frozenset({"parent_id"}),
                ),
                actor_id=uuid4(),
            )

        self.uow.commit.assert_not_awaited()
