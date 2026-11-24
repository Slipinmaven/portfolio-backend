from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.infrastructure.database.models.enums import ResourceStatus, ResourceType


ResourceTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
ResourceUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
ResourceCreator = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)]
ResourceSummary = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class ResourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ResourceTitle
    url: ResourceUrl
    resource_type: ResourceType
    creator: ResourceCreator | None = None
    summary: ResourceSummary | None = None
    commentary: str | None = None


class ResourceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ResourceTitle | None = None
    url: ResourceUrl | None = None
    resource_type: ResourceType | None = None
    creator: ResourceCreator | None = None
    summary: ResourceSummary | None = None
    commentary: str | None = None
    status: ResourceStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one resource field must be provided.")
        nullable_fields = {"creator", "summary", "commentary"}
        for field in self.model_fields_set - nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class ResourceAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    url: str
    resource_type: ResourceType
    creator: str | None
    summary: str | None
    commentary: str | None
    status: ResourceStatus
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResourceAdminListResponse(BaseModel):
    resources: list[ResourceAdminResponse]
    total: int
    offset: int
    limit: int


class PublicResourceResponse(ResourceAdminResponse):
    commentary_html: str


class ResourceLinkResponse(BaseModel):
    id: UUID
    title: str
    url: str
    resource_type: ResourceType
    creator: str | None
    summary: str | None
    commentary_html: str


class PublicResourceListResponse(BaseModel):
    resources: list[PublicResourceResponse]
    total: int
    offset: int
    limit: int
