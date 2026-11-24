from dataclasses import dataclass
from typing import BinaryIO, Literal
from uuid import UUID

from app.infrastructure.database.models.enums import MediaKind, ProjectMediaRole


@dataclass(frozen=True)
class MediaListFilters:
    offset: int = 0
    limit: int = 50
    kind: MediaKind | None = None
    query: str | None = None
    unused_only: bool = False


@dataclass(frozen=True)
class MediaLinkInput:
    url: str
    label: str | None = None
    display_order: int = 0


@dataclass(frozen=True)
class MediaUploadInput:
    filename: str
    source: BinaryIO
    title: str | None = None
    alt_text: str | None = None


@dataclass(frozen=True)
class MediaUpdateInput:
    title: str | None = None
    alt_text: str | None = None
    links: tuple[MediaLinkInput, ...] | None = None
    fields_set: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MediaUploadResult:
    media_id: UUID
    duplicate_checksum: bool


@dataclass(frozen=True)
class MediaStorageCategory:
    kind: MediaKind
    item_count: int
    size_bytes: int


@dataclass(frozen=True)
class MediaStorageFile:
    id: UUID
    kind: MediaKind
    original_filename: str
    title: str | None
    size_bytes: int


@dataclass(frozen=True)
class MediaStorageSummary:
    item_count: int
    size_bytes: int
    categories: tuple[MediaStorageCategory, ...]
    largest_files: tuple[MediaStorageFile, ...]
    storage_provider: Literal["local", "supabase"]
    filesystem_total_bytes: int | None
    filesystem_free_bytes: int | None
    filesystem_free_percent: float | None
    warning_threshold_free_percent: int
    is_low_storage: bool


@dataclass(frozen=True)
class MediaUsageData:
    usage_type: Literal["PROJECT", "SITE_SETTINGS"]
    project_id: UUID | None = None
    project_title: str | None = None
    project_slug: str | None = None
    role: ProjectMediaRole | None = None
    display_order: int | None = None
    caption: str | None = None
    setting: str | None = None
