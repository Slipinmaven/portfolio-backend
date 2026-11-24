from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.categories.dto import (
    CategoryMoveDirection,
    CategoryListFilters,
    CreateCategoryData,
    UpdateCategoryData,
)
from app.application.errors import ConflictError, ResourceNotFoundError
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.category import Category
from app.infrastructure.database.unit_of_work.catalog import CatalogUnitOfWork


MAX_CATEGORY_DEPTH = 4


class CategoryService:
    def __init__(self, unit_of_work: CatalogUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_categories(
        self,
        filters: CategoryListFilters,
    ) -> tuple[list[Category], int]:
        return await self._unit_of_work.categories.list_categories(
            offset=filters.offset,
            limit=filters.limit,
            is_active=filters.is_active,
        )

    async def get_category(self, category_id: UUID) -> Category:
        category = await self._unit_of_work.categories.get_by_id(category_id)
        if category is None:
            raise ResourceNotFoundError("Category not found.")
        return category

    async def get_active_category(self, category_id: UUID) -> Category:
        category = await self._unit_of_work.categories.get_by_id(category_id)
        if category is None or not category.is_active:
            raise ResourceNotFoundError("Category not found.")
        return category

    async def get_active_category_by_slug(self, slug: str) -> Category:
        category = await self._unit_of_work.categories.get_active_by_slug(slug)
        if category is None:
            raise ResourceNotFoundError("Category not found.")
        return category

    async def create_category(
        self,
        data: CreateCategoryData,
        *,
        actor_id: UUID,
    ) -> Category:
        parent_depth = await self._validate_parent(None, data.parent_id)
        if parent_depth + 1 > MAX_CATEGORY_DEPTH:
            raise ConflictError(
                f"Categories cannot be nested more than {MAX_CATEGORY_DEPTH} levels deep."
            )

        category = Category(
            name=data.name.strip(),
            slug=data.slug.strip(),
            description=data.description.strip() if data.description else data.description,
            parent_id=data.parent_id,
            display_order=data.display_order,
            is_active=data.is_active,
        )
        try:
            await self._unit_of_work.categories.create(category)
            await self._record_audit(
                actor_id=actor_id,
                category_id=category.id,
                action="category.created",
                new_values={
                    "name": category.name,
                    "slug": category.slug,
                    "parent_id": str(category.parent_id) if category.parent_id else None,
                },
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "A category with this slug or sibling name already exists."
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return category

    async def update_category(
        self,
        category_id: UUID,
        data: UpdateCategoryData,
        *,
        actor_id: UUID,
    ) -> Category:
        category = await self.get_category(category_id)
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}

        if (
            "parent_id" in data.fields_set
            and category.parent_id != data.parent_id
        ):
            parent_depth = await self._validate_parent(category, data.parent_id)
            subtree_height = await self._get_subtree_height(category)
            if parent_depth + subtree_height > MAX_CATEGORY_DEPTH:
                raise ConflictError(
                    f"Categories cannot be nested more than {MAX_CATEGORY_DEPTH} levels deep."
                )
        for field in ("name", "slug", "description", "parent_id", "display_order", "is_active"):
            if field not in data.fields_set:
                continue
            value = getattr(data, field)
            if field in {"name", "slug"} and isinstance(value, str):
                value = value.strip()
            if field == "description" and isinstance(value, str):
                value = value.strip()
            if field == "parent_id":
                value = str(value) if value is not None else None
                old_value = str(category.parent_id) if category.parent_id else None
                if old_value == value:
                    continue
                old_values[field] = old_value
                new_values[field] = value
                category.parent_id = data.parent_id
                continue
            old_value = getattr(category, field)
            if old_value == value:
                continue
            old_values[field] = old_value
            new_values[field] = value
            setattr(category, field, value)

        try:
            if new_values:
                await self._record_audit(
                    actor_id=actor_id,
                    category_id=category.id,
                    action="category.updated",
                    old_values=old_values,
                    new_values=new_values,
                )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "The category update conflicts with an existing category or reference."
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return category

    async def move_category(
        self,
        category_id: UUID,
        direction: CategoryMoveDirection,
        *,
        actor_id: UUID,
    ) -> Category:
        category = await self._unit_of_work.categories.get_by_id(category_id)
        if category is None:
            raise ResourceNotFoundError("Category not found.")

        try:
            siblings = await self._unit_of_work.categories.list_siblings_for_update(
                category.parent_id
            )
            siblings.sort(key=lambda sibling: (sibling.display_order, sibling.id))
            current_index = next(
                (
                    index
                    for index, sibling in enumerate(siblings)
                    if sibling.id == category.id
                ),
                None,
            )
            if current_index is None:
                raise ConflictError(
                    "The category order changed. Refresh the list and try again."
                )

            next_index = current_index + (-1 if direction == "up" else 1)
            if next_index < 0 or next_index >= len(siblings):
                await self._unit_of_work.commit()
                return category

            old_order = category.display_order
            siblings[current_index], siblings[next_index] = (
                siblings[next_index],
                siblings[current_index],
            )
            for display_order, sibling in enumerate(siblings):
                sibling.display_order = display_order

            await self._record_audit(
                actor_id=actor_id,
                category_id=category.id,
                action="category.reordered",
                old_values={
                    "parent_id": str(category.parent_id)
                    if category.parent_id
                    else None,
                    "display_order": old_order,
                },
                new_values={
                    "parent_id": str(category.parent_id)
                    if category.parent_id
                    else None,
                    "display_order": category.display_order,
                },
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError("The category order could not be updated.") from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise

        return category

    async def delete_category(self, category_id: UUID, *, actor_id: UUID) -> None:
        category = await self.get_category(category_id)
        try:
            await self._unit_of_work.categories.delete(category)
            await self._record_audit(
                actor_id=actor_id,
                category_id=category.id,
                action="category.deleted",
                old_values={"name": category.name, "slug": category.slug},
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "The category cannot be deleted while it has children or projects."
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise

    async def _require_category(self, category_id: UUID) -> Category:
        category = await self._unit_of_work.categories.get_by_id(category_id)
        if category is None:
            raise ResourceNotFoundError("Parent category not found.")
        return category

    async def _validate_parent(
        self,
        category: Category | None,
        parent_id: UUID | None,
    ) -> int:
        visited: set[UUID] = set()
        current_id = parent_id
        depth = 0
        while current_id is not None:
            if (category is not None and current_id == category.id) or current_id in visited:
                raise ConflictError("A category cannot be its own ancestor.")
            visited.add(current_id)
            parent = await self._require_category(current_id)
            current_id = parent.parent_id
            depth += 1
        return depth

    async def _get_subtree_height(self, category: Category) -> int:
        max_depth = 1
        pending = [(category, 1)]
        visited = {category.id}
        while pending:
            current, depth = pending.pop()
            for child in await self._unit_of_work.categories.get_children(current.id):
                if child.id in visited:
                    raise ConflictError("The category hierarchy contains a cycle.")
                visited.add(child.id)
                child_depth = depth + 1
                max_depth = max(max_depth, child_depth)
                pending.append((child, child_depth))
        return max_depth

    async def _record_audit(
        self,
        *,
        actor_id: UUID,
        category_id: UUID,
        action: str,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> None:
        await self._unit_of_work.audit_logs.create(
            AuditLog(
                user_id=actor_id,
                action=action,
                entity_type="category",
                entity_id=category_id,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )
        )
