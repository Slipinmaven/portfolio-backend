from typing import Annotated, Self
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator


TagName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
TagSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
    ),
]
TagDescription = Annotated[str, StringConstraints(max_length=500)]


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TagListResponse(BaseModel):
    tags: list[TagResponse]
    total: int
    offset: int
    limit: int


class CreateTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TagName
    slug: TagSlug
    description: TagDescription | None = None
    is_active: bool = False


class UpdateTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TagName | None = None
    slug: TagSlug | None = None
    description: TagDescription | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one tag field must be provided.")
        for field in self.model_fields_set - {"description"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self
