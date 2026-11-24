from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.infrastructure.database.models.enums import (
    PostKind,
    PostStatus,
)
from app.presentation.schemas.resources import ResourceLinkResponse


class PostListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)
    kind: PostKind | None = None
    status: PostStatus | None = None
    category_id: UUID | None = None


class PostCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PostKind
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
    summary: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    ] = None
    body: str = ""
    category_ids: list[UUID] = Field(default_factory=list)
    attachment_media_ids: list[UUID] = Field(default_factory=list)
    project_ids: list[UUID] = Field(default_factory=list)
    resource_ids: list[UUID] = Field(default_factory=list)


class PostUpdateRequest(BaseModel):
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
    summary: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    ] = None
    body: str | None = None
    status: PostStatus | None = None
    category_ids: list[UUID] | None = None
    attachment_media_ids: list[UUID] | None = None
    project_ids: list[UUID] | None = None
    resource_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one post field must be provided.")
        for field in self.model_fields_set - {"summary"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class MarkdownPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str


class MarkdownPreviewResponse(BaseModel):
    html: str


class PostCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class PostAttachmentResponse(BaseModel):
    media_id: UUID
    title: str | None
    original_filename: str
    mime_type: str
    size_bytes: int
    file_url: str


class PostProjectResponse(BaseModel):
    id: UUID
    title: str
    slug: str
    short_description: str


class PostAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: PostKind
    title: str
    slug: str
    summary: str | None
    body: str
    status: PostStatus
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    category_ids: list[UUID]
    project_ids: list[UUID]
    resource_ids: list[UUID]
    attachments: list[PostAttachmentResponse]


class PostAdminListResponse(BaseModel):
    posts: list[PostAdminResponse]
    total: int
    offset: int
    limit: int


class PublicPostSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: PostKind
    title: str
    slug: str
    summary: str | None
    published_at: datetime
    categories: list[PostCategoryResponse]


class PublicPostResponse(PublicPostSummaryResponse):
    body_html: str
    attachments: list[PostAttachmentResponse]
    related_projects: list[PostProjectResponse]
    resources: list[ResourceLinkResponse]


class PublicPostListResponse(BaseModel):
    posts: list[PublicPostSummaryResponse]
    total: int
    offset: int
    limit: int
