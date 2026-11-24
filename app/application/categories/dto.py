from dataclasses import dataclass
from typing import Literal
from uuid import UUID

CategoryMoveDirection = Literal["up", "down"]


@dataclass(frozen=True)
class CreateCategoryData:
    name: str
    slug: str
    display_order: int = 0
    description: str | None = None
    parent_id: UUID | None = None
    is_active: bool = False


@dataclass(frozen=True)
class UpdateCategoryData:
    name: str | None
    slug: str | None
    description: str | None
    parent_id: UUID | None
    display_order: int | None
    is_active: bool | None
    fields_set: frozenset[str]


@dataclass(frozen=True)
class CategoryListFilters:
    offset: int = 0
    limit: int = 50
    is_active: bool | None = None
