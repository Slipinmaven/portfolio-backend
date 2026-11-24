from uuid import UUID
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing import Annotated, Self

from app.infrastructure.database.models.enums import MediaKind, ProjectMediaRole
from app.infrastructure.database.models.project_media import ProjectMedia


class ProjectMediaCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: UUID
    role: ProjectMediaRole
    display_order: int = Field(default=0, ge=0)
    caption: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class ProjectMediaUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_order: int | None = Field(default=None, ge=0)
    caption: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None

    @model_validator(mode="after")
    def require_update_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class ProjectMediaOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ProjectMediaRole
    media_ids: list[UUID]


class ProjectMediaLinkResponse(BaseModel):
    url: str
    label: str | None
    display_order: int


class ProjectMediaResponse(BaseModel):
    project_id: UUID
    media_id: UUID
    role: ProjectMediaRole
    display_order: int
    caption: str | None
    original_filename: str
    kind: MediaKind
    title: str | None
    alt_text: str | None
    mime_type: str
    width: int | None
    height: int | None
    duration_seconds: int | None
    file_url: str
    poster_url: str | None
    links: list[ProjectMediaLinkResponse] = Field(default_factory=list)


class ProjectCoverMediaResponse(BaseModel):
    media_id: UUID
    title: str | None
    alt_text: str | None
    file_url: str


class ProjectMediaListResponse(BaseModel):
    media: list[ProjectMediaResponse]


def project_cover_media_response(
    association: ProjectMedia,
) -> ProjectCoverMediaResponse:
    media = association.media
    return ProjectCoverMediaResponse(
        media_id=media.id,
        title=media.title,
        alt_text=media.alt_text,
        file_url=f"/api/v1/media/{media.id}/content",
    )


def project_media_response(association: ProjectMedia) -> ProjectMediaResponse:
    media = association.media
    is_video = media.kind == MediaKind.VIDEO
    return ProjectMediaResponse(
        project_id=association.project_id,
        media_id=media.id,
        role=association.role,
        display_order=association.display_order,
        caption=association.caption,
        original_filename=media.original_filename,
        kind=media.kind,
        title=media.title,
        alt_text=media.alt_text,
        mime_type=media.mime_type,
        width=media.width,
        height=media.height,
        duration_seconds=media.duration_seconds,
        file_url=f"/api/v1/media/{media.id}/content",
        poster_url=f"/api/v1/media/{media.id}/poster" if is_video else None,
        links=[
            ProjectMediaLinkResponse(
                url=link.url,
                label=link.label,
                display_order=link.display_order,
            )
            for link in sorted(
                media.links,
                key=lambda link: (link.display_order, link.created_at, link.id),
            )
        ],
    )
