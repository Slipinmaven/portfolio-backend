import asyncio
from uuid import UUID
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.application.media.dto import (
    MediaLinkInput,
    MediaListFilters,
    MediaUpdateInput,
    MediaUploadInput,
)
from app.application.media.service import MediaService
from app.infrastructure.database.models.enums import MediaKind
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_media_service
from app.presentation.schemas.media import (
    MediaLinkResponse,
    MediaListRequest,
    MediaListResponse,
    MediaResponse,
    MediaStorageSummaryResponse,
    MediaUpdateRequest,
    MediaUsageListResponse,
    MediaUsageResponse,
    MediaUploadJobResponse,
)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/admin", response_model=MediaListResponse)
async def list_media(
    query: MediaListRequest = Depends(),
    _editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaListResponse:
    items, total = await media_service.list_media(
        MediaListFilters(
            offset=query.offset,
            limit=query.limit,
            kind=query.kind,
            query=query.query,
            unused_only=query.unused_only,
        )
    )
    return MediaListResponse(
        media=[_media_response(item) for item in items],
        total=total,
        offset=query.offset,
        limit=query.limit,
    )


@router.get(
    "/admin/storage-usage",
    response_model=MediaStorageSummaryResponse,
)
async def get_media_storage_usage(
    _editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaStorageSummaryResponse:
    summary = await media_service.get_storage_summary()
    return MediaStorageSummaryResponse(
        item_count=summary.item_count,
        size_bytes=summary.size_bytes,
        categories=[
            {
                "kind": category.kind,
                "item_count": category.item_count,
                "size_bytes": category.size_bytes,
            }
            for category in summary.categories
        ],
        largest_files=[
            {
                "id": media.id,
                "kind": media.kind,
                "original_filename": media.original_filename,
                "title": media.title,
                "size_bytes": media.size_bytes,
            }
            for media in summary.largest_files
        ],
        storage_provider=summary.storage_provider,
        filesystem_total_bytes=summary.filesystem_total_bytes,
        filesystem_free_bytes=summary.filesystem_free_bytes,
        filesystem_free_percent=summary.filesystem_free_percent,
        warning_threshold_free_percent=summary.warning_threshold_free_percent,
        is_low_storage=summary.is_low_storage,
    )


@router.post(
    "/admin/upload",
    response_model=MediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=200),
    alt_text: str | None = Form(default=None, max_length=500),
    upload_id: UUID | None = Form(default=None),
    editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaResponse:
    if upload_id is not None:
        job, existing_media, should_process = await media_service.begin_upload_job(
            upload_id,
            actor_id=editor.id,
        )
        if not should_process:
            if job.status == "PROCESSING":
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"status": "PROCESSING"},
                )
            if existing_media is not None:
                return _media_response(existing_media)

    try:
        media, duplicate_media = await media_service.upload_media(
            MediaUploadInput(
                filename=file.filename or "upload",
                source=file.file,
                title=title,
                alt_text=alt_text,
            ),
            actor_id=editor.id,
            upload_job_id=upload_id,
        )
    except asyncio.CancelledError:
        if upload_id is not None:
            await media_service.fail_upload_job(upload_id)
        raise
    except Exception:
        if upload_id is not None:
            await media_service.fail_upload_job(upload_id)
        raise
    return _media_response(
        media,
        duplicate_media=duplicate_media,
    )


@router.get(
    "/admin/upload-jobs/{upload_id}",
    response_model=MediaUploadJobResponse,
)
async def get_media_upload_job(
    upload_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaUploadJobResponse:
    job, media, duplicate_media = await media_service.get_upload_job(
        upload_id,
        actor_id=editor.id,
    )
    return MediaUploadJobResponse(
        status=job.status,
        media=(
            _media_response(media, duplicate_media=duplicate_media)
            if media is not None
            else None
        ),
    )


@router.get("/admin/{media_id}/usages", response_model=MediaUsageListResponse)
async def list_media_usages(
    media_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaUsageListResponse:
    usages = await media_service.list_usages(media_id)
    return MediaUsageListResponse(
        usages=[
            MediaUsageResponse(
                usage_type=usage.usage_type,
                project_id=usage.project_id,
                project_title=usage.project_title,
                project_slug=usage.project_slug,
                role=usage.role,
                display_order=usage.display_order,
                caption=usage.caption,
                setting=usage.setting,
            )
            for usage in usages
        ]
    )


@router.get("/admin/{media_id}/poster")
async def get_admin_video_poster(
    media_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> Response:
    asset = await media_service.get_admin_video_poster(media_id)
    return _poster_response(asset)


@router.get("/admin/{media_id}/content")
async def get_admin_media_content(
    media_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> Response:
    media, asset = await media_service.get_admin_stored_file(media_id)
    return _media_file_response(media, asset)


@router.get("/admin/{media_id}", response_model=MediaResponse)
async def get_media(
    media_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaResponse:
    return _media_response(await media_service.get_media(media_id))


@router.patch("/admin/{media_id}", response_model=MediaResponse)
async def update_media(
    media_id: UUID,
    request: MediaUpdateRequest,
    editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> MediaResponse:
    updated = await media_service.update_media(
        media_id,
        MediaUpdateInput(
            title=request.title,
            alt_text=request.alt_text,
            links=(
                tuple(
                    MediaLinkInput(
                        url=link.url,
                        label=link.label,
                        display_order=link.display_order,
                    )
                    for link in request.links
                )
                if request.links is not None
                else None
            ),
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=editor.id,
    )
    return _media_response(updated)


@router.delete("/admin/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    media_service: MediaService = Depends(get_media_service),
) -> None:
    await media_service.delete_media(media_id, actor_id=editor.id)


@router.get("/{media_id}/poster")
async def get_video_poster(
    media_id: UUID,
    media_service: MediaService = Depends(get_media_service),
) -> Response:
    asset = await media_service.get_public_video_poster(media_id)
    return _poster_response(asset)


@router.get("/{media_id}/content")
async def get_media_content(
    media_id: UUID,
    media_service: MediaService = Depends(get_media_service),
) -> Response:
    media, asset = await media_service.get_public_stored_file(media_id)
    return _media_file_response(media, asset)


def _media_file_response(media: Media, asset: Path | str | bytes) -> Response:
    if isinstance(asset, str):
        return RedirectResponse(asset, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    is_document = media.kind == MediaKind.DOCUMENT
    content_disposition_type = "attachment" if is_document else "inline"
    if isinstance(asset, bytes):
        return Response(
            content=asset,
            media_type=media.mime_type,
            headers={
                "Content-Disposition": (
                    f"{content_disposition_type}; "
                    f"filename*=UTF-8''{quote(media.original_filename)}"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )
    return FileResponse(
        asset,
        media_type=media.mime_type,
        filename=media.original_filename,
        content_disposition_type=content_disposition_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _poster_response(asset: Path | str | bytes) -> Response:
    if isinstance(asset, str):
        return RedirectResponse(asset, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    if isinstance(asset, bytes):
        return Response(
            content=asset,
            media_type="image/jpeg",
            headers={"X-Content-Type-Options": "nosniff"},
        )
    return FileResponse(
        asset,
        media_type="image/jpeg",
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _media_response(
    media: Media,
    *,
    duplicate_media: Media | None = None,
) -> MediaResponse:
    is_video = media.kind == MediaKind.VIDEO
    return MediaResponse(
        id=media.id,
        kind=media.kind,
        original_filename=media.original_filename,
        mime_type=media.mime_type,
        size_bytes=media.size_bytes,
        checksum_sha256=media.checksum_sha256,
        title=media.title,
        alt_text=media.alt_text,
        width=media.width,
        height=media.height,
        duration_seconds=media.duration_seconds,
        created_at=media.created_at,
        updated_at=media.updated_at,
        file_url=f"/api/v1/media/{media.id}/content",
        poster_url=f"/api/v1/media/{media.id}/poster" if is_video else None,
        links=[
            MediaLinkResponse.model_validate(link)
            for link in sorted(
                media.links,
                key=lambda link: (link.display_order, link.created_at, link.id),
            )
        ],
        duplicate_checksum=duplicate_media is not None,
        duplicate_media_id=duplicate_media.id if duplicate_media else None,
    )
