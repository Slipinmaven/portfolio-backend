from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.application.pages.blocks import PageBlock
from app.infrastructure.database.models.enums import (
    PageStatus,
    PageRevisionState,
    PostKind,
    PostStatus,
    ProjectStatus,
)


class PageListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)
    status: PageStatus | None = None


class PageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=120,
            pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
        ),
    ]
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ]


class PageDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=120,
            pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$",
        ),
    ]
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ]
    summary: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=300),
    ] = None
    sections: list[PageBlock]


class PagePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_note: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=300),
    ] = None


class PageMarkdownPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str


class PageMarkdownPreviewResponse(BaseModel):
    html: str


class PageRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_id: UUID
    revision_number: int
    state: PageRevisionState
    title: str
    summary: str | None
    sections: list[PageBlock]
    schema_version: int
    change_note: str | None
    published_at: datetime | None
    superseded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PageSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    system_key: str | None
    status: PageStatus
    title: str
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    draft_revision_number: int | None


class PageDetailResponse(PageSummaryResponse):
    draft_revision: PageRevisionResponse | None
    published_revision: PageRevisionResponse | None


class PageListResponse(BaseModel):
    pages: list[PageSummaryResponse]
    total: int
    offset: int
    limit: int


class PageRevisionListResponse(BaseModel):
    page_id: UUID
    revisions: list[PageRevisionResponse]


class PublicPageImageResponse(BaseModel):
    id: UUID
    title: str | None
    alt_text: str | None
    width: int | None
    height: int | None


class PublicPageProjectCoverResponse(BaseModel):
    media_id: UUID
    title: str | None
    alt_text: str | None
    file_url: str


class PublicPageProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    short_description: str
    demo_url: str | None
    github_url: str | None
    status: ProjectStatus
    is_featured: bool
    display_order: int
    cover_media: PublicPageProjectCoverResponse | None = None


class PublicPageLinkTargetResponse(BaseModel):
    id: UUID
    slug: str
    status: PageStatus


class PublicPostLinkTargetResponse(BaseModel):
    id: UUID
    kind: PostKind
    slug: str
    status: PostStatus


class PublicPageResponse(BaseModel):
    slug: str
    system_key: str | None
    title: str
    summary: str | None
    published_at: datetime
    sections: list[PageBlock]
    images: list[PublicPageImageResponse]
    projects: list[PublicPageProjectResponse]
    pages: list[PublicPageLinkTargetResponse]
    posts: list[PublicPostLinkTargetResponse]
    rendered_markdown: dict[str, str]
