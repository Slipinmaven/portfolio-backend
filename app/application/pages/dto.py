from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.application.pages.blocks import PageBlock
from app.infrastructure.database.models.enums import PageStatus

if TYPE_CHECKING:
    from app.infrastructure.database.models.media import Media
    from app.infrastructure.database.models.page import Page
    from app.infrastructure.database.models.post import Post
    from app.infrastructure.database.models.project import Project
    from app.infrastructure.database.models.project_media import ProjectMedia


@dataclass(frozen=True)
class PageListFilters:
    offset: int = 0
    limit: int = 50
    status: PageStatus | None = None


@dataclass(frozen=True)
class PageCreateDTO:
    slug: str
    title: str


@dataclass(frozen=True)
class PageDraftDTO:
    slug: str
    title: str
    summary: str | None
    sections: list[dict[str, object]]


@dataclass(frozen=True)
class PublicPageData:
    slug: str
    title: str
    summary: str | None
    published_at: datetime
    sections: list[PageBlock]
    images: list[Media]
    projects: list[Project]
    pages: list[Page]
    posts: list[Post]
    project_covers: dict[UUID, ProjectMedia] = field(default_factory=dict)
    system_key: str | None = None

