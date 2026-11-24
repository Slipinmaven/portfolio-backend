from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.infrastructure.database.models.enums import DevelopmentStatus, ProjectStatus


@dataclass(frozen=True)
class ProjectListFilters:
    offset: int = 0
    limit: int = 50
    status: ProjectStatus | None = None
    development_status: DevelopmentStatus | None = None
    is_featured: bool | None = None
    category_id: UUID | None = None
    tag_id: UUID | None = None
    active_catalog_only: bool = False


@dataclass(frozen=True)
class ProjectCreateDTO:
    title: str
    slug: str
    short_description: str
    development_status: DevelopmentStatus
    display_order: int
    github_url: str | None = None
    demo_url: str | None = None
    overview: str | None = None
    status: ProjectStatus = ProjectStatus.DRAFT
    published_at: datetime | None = None
    archived_at: datetime | None = None
    is_featured: bool = False
    category_ids: tuple[UUID, ...] = ()
    tag_ids: tuple[UUID, ...] = ()
    resource_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ProjectUpdateDTO:
    title: str | None = None
    slug: str | None = None
    short_description: str | None = None
    development_status: DevelopmentStatus | None = None
    display_order: int | None = None
    github_url: str | None = None
    demo_url: str | None = None
    overview: str | None = None
    status: ProjectStatus | None = None
    published_at: datetime | None = None
    archived_at: datetime | None = None
    is_featured: bool | None = None
    category_ids: tuple[UUID, ...] | None = None
    tag_ids: tuple[UUID, ...] | None = None
    resource_ids: tuple[UUID, ...] | None = None
    fields_set: frozenset[str] = frozenset()
