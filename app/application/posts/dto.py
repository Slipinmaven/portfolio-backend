from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.database.models.enums import PostKind, PostStatus


@dataclass(frozen=True)
class PostListFilters:
    offset: int = 0
    limit: int = 50
    kind: PostKind | None = None
    status: PostStatus | None = None
    published_only: bool = False
    category_id: UUID | None = None


@dataclass(frozen=True)
class PostCreateDTO:
    kind: PostKind
    title: str
    slug: str
    summary: str | None = None
    body: str = ""
    category_ids: tuple[UUID, ...] = ()
    attachment_media_ids: tuple[UUID, ...] = ()
    project_ids: tuple[UUID, ...] = ()
    resource_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class PostUpdateDTO:
    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    body: str | None = None
    status: PostStatus | None = None
    category_ids: tuple[UUID, ...] | None = None
    attachment_media_ids: tuple[UUID, ...] | None = None
    project_ids: tuple[UUID, ...] | None = None
    resource_ids: tuple[UUID, ...] | None = None
    fields_set: frozenset[str] = frozenset()
