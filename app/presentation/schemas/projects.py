from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from typing import Annotated, Self

from app.infrastructure.database.models.enums import DevelopmentStatus, ProjectStatus
from app.presentation.schemas.project_media import (
    ProjectCoverMediaResponse,
    ProjectMediaResponse,
)
from app.presentation.schemas.resources import ResourceLinkResponse


class ProjectSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    github_url: str | None
    demo_url: str | None
    short_description: str
    overview: str | None
    status: ProjectStatus
    development_status: DevelopmentStatus
    published_at: datetime | None
    archived_at: datetime | None
    display_order: int
    is_featured: bool
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummaryResponse]
    total: int
    offset: int
    limit: int


class PublicProjectSummaryResponse(ProjectSummaryResponse):
    cover_media: ProjectCoverMediaResponse | None


class PublicProjectListResponse(BaseModel):
    projects: list[PublicProjectSummaryResponse]
    total: int
    offset: int
    limit: int


class ProjectListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)
    development_status: DevelopmentStatus | None = None
    is_featured: bool | None = None
    category_id: UUID | None = None
    tag_id: UUID | None = None


class ProjectAdminListRequest(ProjectListRequest):
    status: ProjectStatus | None = None


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    slug: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=220,
            pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
        ),
    ]
    short_description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    development_status: DevelopmentStatus
    display_order: int = Field(ge=0)
    github_url: Annotated[str, StringConstraints(max_length=500)] | None = None
    demo_url: Annotated[str, StringConstraints(max_length=500)] | None = None
    overview: str | None = None
    status: ProjectStatus = ProjectStatus.DRAFT
    published_at: datetime | None = None
    archived_at: datetime | None = None
    is_featured: bool = False
    category_ids: list[UUID] = Field(default_factory=list)
    tag_ids: list[UUID] = Field(default_factory=list)
    resource_ids: list[UUID] = Field(default_factory=list)

    @field_validator("github_url", "demo_url")
    @classmethod
    def require_http_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://.")
        return value

    @model_validator(mode="after")
    def validate_status_timestamps(self) -> Self:
        if self.status == ProjectStatus.PUBLISHED and self.published_at is None:
            raise ValueError("published_at is required for published projects.")
        if (self.status == ProjectStatus.ARCHIVED) != (self.archived_at is not None):
            raise ValueError("archived_at must be set exactly when status is ARCHIVED.")
        return self


class ProjectCreateResponse(ProjectSummaryResponse):
    category_ids: list[UUID]
    tag_ids: list[UUID]
    resource_ids: list[UUID]


class ProjectDetailResponse(ProjectSummaryResponse):
    category_ids: list[UUID]
    tag_ids: list[UUID]
    resource_ids: list[UUID]
    media: list[ProjectMediaResponse] = Field(default_factory=list)


class PublicProjectTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class PublicProjectDetailResponse(ProjectDetailResponse):
    overview_html: str
    tags: list[PublicProjectTagResponse] = Field(default_factory=list)
    resources: list[ResourceLinkResponse] = Field(default_factory=list)


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ] | None = None
    slug: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=220,
            pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
        ),
    ] | None = None
    short_description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ] | None = None
    development_status: DevelopmentStatus | None = None
    display_order: int | None = Field(default=None, ge=0)
    github_url: Annotated[str, StringConstraints(max_length=500)] | None = None
    demo_url: Annotated[str, StringConstraints(max_length=500)] | None = None
    overview: str | None = None
    status: ProjectStatus | None = None
    published_at: datetime | None = None
    archived_at: datetime | None = None
    is_featured: bool | None = None
    category_ids: list[UUID] | None = None
    tag_ids: list[UUID] | None = None
    resource_ids: list[UUID] | None = None

    @field_validator("github_url", "demo_url")
    @classmethod
    def require_http_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://.")
        return value

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one project field must be provided.")
        nullable_fields = {
            "github_url",
            "demo_url",
            "overview",
            "published_at",
            "archived_at",
        }
        for field in self.model_fields_set - nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self
