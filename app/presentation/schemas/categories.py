from uuid import UUID
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
CategorySlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
    ),
]
CategoryDescription = Annotated[str, StringConstraints(max_length=500)]


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID | None
    name: str
    slug: str
    description: str | None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryListResponse(BaseModel):
    categories: list[CategoryResponse]
    total: int
    offset: int
    limit: int


class CreateCategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CategoryName
    slug: CategorySlug
    description: CategoryDescription | None = None
    parent_id: UUID | None = None
    display_order: int = Field(default=0, ge=0)
    is_active: bool = False


class UpdateCategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CategoryName | None = None
    slug: CategorySlug | None = None
    description: CategoryDescription | None = None
    parent_id: UUID | None = None
    display_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one category field must be provided.")
        nullable_fields = {"description", "parent_id"}
        for field in self.model_fields_set - nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class MoveCategoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["up", "down"]
