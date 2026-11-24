from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from typing import Annotated, Literal, Self

from app.infrastructure.database.models.enums import MediaKind, ProjectMediaRole

HttpsUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=9, max_length=500)]


class MediaLinkInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpsUrl
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    display_order: int = Field(default=0, ge=0)

    @field_validator("url")
    @classmethod
    def require_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("External media links must use a valid https:// URL.")
        return value


class MediaUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    alt_text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    links: list[MediaLinkInputRequest] | None = None

    @model_validator(mode="after")
    def require_update_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class MediaListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)
    kind: MediaKind | None = None
    query: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    unused_only: bool = False


class MediaLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    label: str | None
    display_order: int
    created_at: datetime


class MediaResponse(BaseModel):
    id: UUID
    kind: MediaKind
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    title: str | None
    alt_text: str | None
    width: int | None
    height: int | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime
    file_url: str
    poster_url: str | None
    links: list[MediaLinkResponse] = Field(default_factory=list)
    duplicate_checksum: bool = False
    duplicate_media_id: UUID | None = None


class MediaUploadJobResponse(BaseModel):
    status: Literal["PROCESSING", "SUCCEEDED", "FAILED"]
    media: MediaResponse | None = None


class MediaListResponse(BaseModel):
    media: list[MediaResponse]
    total: int
    offset: int
    limit: int


class MediaStorageCategoryResponse(BaseModel):
    kind: MediaKind
    item_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)


class MediaStorageFileResponse(BaseModel):
    id: UUID
    kind: MediaKind
    original_filename: str
    title: str | None
    size_bytes: int = Field(ge=0)


class MediaStorageSummaryResponse(BaseModel):
    item_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    categories: list[MediaStorageCategoryResponse]
    largest_files: list[MediaStorageFileResponse]
    filesystem_total_bytes: int = Field(ge=1)
    filesystem_free_bytes: int = Field(ge=0)
    filesystem_free_percent: float = Field(ge=0, le=100)
    warning_threshold_free_percent: int = Field(ge=1, le=99)
    is_low_storage: bool


class MediaUsageResponse(BaseModel):
    usage_type: Literal["PROJECT", "SITE_SETTINGS"]
    project_id: UUID | None = None
    project_title: str | None = None
    project_slug: str | None = None
    role: ProjectMediaRole | None = None
    display_order: int | None = None
    caption: str | None = None
    setting: str | None = None


class MediaUsageListResponse(BaseModel):
    usages: list[MediaUsageResponse]
