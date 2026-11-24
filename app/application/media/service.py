import asyncio
import logging
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.application.errors import (
    ConflictError,
    MediaStorageError,
    MediaUploadTooLargeError,
    MediaValidationError,
    ResourceNotFoundError,
)
from app.application.pages.media_references import collect_page_media_ids_from_sections
from app.application.media.dto import (
    MediaListFilters,
    MediaStorageCategory,
    MediaStorageFile,
    MediaStorageSummary,
    MediaUsageData,
    MediaUpdateInput,
    MediaUploadInput,
)
from app.core.config import Settings, settings
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import (
    MediaKind,
    ProjectStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.media_upload_job import MediaUploadJob
from app.infrastructure.database.models.media_link import MediaLink
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.unit_of_work.media import MediaUnitOfWork
from app.infrastructure.media_processing.processor import MediaProcessor
from app.infrastructure.storage.local_media_storage import LocalMediaStorage
from app.infrastructure.storage.supabase_media_storage import SupabaseMediaStorage

logger = logging.getLogger(__name__)

_SAFE_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_STORAGE_OVERVIEW_LARGEST_FILES = 5


class MediaService:
    def __init__(
        self,
        unit_of_work: MediaUnitOfWork,
        configuration: Settings = settings,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._configuration = configuration
        if configuration.media_storage_provider == "supabase":
            secret_key = configuration.supabase_secret_key.get_secret_value()
            legacy_service_role_key = (
                configuration.supabase_service_role_key.get_secret_value()
            )
            self._storage: LocalMediaStorage | SupabaseMediaStorage = (
                SupabaseMediaStorage(
                    staging_root=configuration.media_directory,
                    project_url=configuration.supabase_url or "",
                    api_key=secret_key or legacy_service_role_key,
                    bucket=configuration.supabase_media_bucket,
                    use_legacy_bearer_auth=not bool(secret_key),
                )
            )
        else:
            self._storage = LocalMediaStorage(configuration.media_directory)
        self._processor = MediaProcessor(
            ffmpeg_binary=configuration.media_ffmpeg_binary,
            ffprobe_binary=configuration.media_ffprobe_binary,
            maximum_video_bytes=configuration.media_video_max_bytes,
            maximum_video_duration_seconds=configuration.media_video_max_duration_seconds,
            video_processing_timeout_seconds=(
                configuration.media_video_processing_timeout_seconds
            ),
        )

    async def list_media(
        self,
        filters: MediaListFilters,
    ) -> tuple[list[Media], int]:
        return await self._unit_of_work.media.list_media(
            offset=filters.offset,
            limit=filters.limit,
            kind=filters.kind,
            query_text=filters.query,
            unused_only=filters.unused_only,
        )

    async def get_storage_summary(self) -> MediaStorageSummary:
        usage_by_kind = {
            kind: (item_count, size_bytes)
            for kind, item_count, size_bytes in (
                await self._unit_of_work.media.get_storage_usage_by_kind()
            )
        }
        video_storage_keys = await self._unit_of_work.media.list_video_storage_keys()
        poster_bytes = 0
        if isinstance(self._storage, LocalMediaStorage):
            poster_bytes = await asyncio.to_thread(
                _sum_video_poster_bytes,
                self._storage,
                video_storage_keys,
            )

        categories = []
        for kind in MediaKind:
            item_count, size_bytes = usage_by_kind.get(kind, (0, 0))
            if kind == MediaKind.VIDEO:
                size_bytes += poster_bytes
            categories.append(
                MediaStorageCategory(
                    kind=kind,
                    item_count=item_count,
                    size_bytes=size_bytes,
                )
            )

        largest_files = await self._unit_of_work.media.list_largest_media(
            limit=_STORAGE_OVERVIEW_LARGEST_FILES
        )
        largest_file_summaries = tuple(
            MediaStorageFile(
                id=media.id,
                kind=media.kind,
                original_filename=media.original_filename,
                title=media.title,
                size_bytes=media.size_bytes,
            )
            for media in largest_files
        )
        filesystem_total_bytes = None
        filesystem_free_bytes = None
        filesystem_free_percent = None
        if isinstance(self._storage, LocalMediaStorage):
            (
                filesystem_total_bytes,
                _,
                filesystem_free_bytes,
            ) = await asyncio.to_thread(
                _get_media_filesystem_usage,
                self._configuration.media_directory,
            )
            filesystem_free_percent = (
                filesystem_free_bytes / filesystem_total_bytes * 100
                if filesystem_total_bytes
                else 0.0
            )
        warning_threshold = (
            self._configuration.media_storage_warning_free_percent
        )
        return MediaStorageSummary(
            item_count=sum(category.item_count for category in categories),
            size_bytes=sum(category.size_bytes for category in categories),
            categories=tuple(categories),
            largest_files=largest_file_summaries,
            storage_provider=self._configuration.media_storage_provider,
            filesystem_total_bytes=filesystem_total_bytes,
            filesystem_free_bytes=filesystem_free_bytes,
            filesystem_free_percent=filesystem_free_percent,
            warning_threshold_free_percent=warning_threshold,
            is_low_storage=(
                filesystem_free_percent is not None
                and filesystem_free_percent <= warning_threshold
            ),
        )

    async def get_media(self, media_id: UUID) -> Media:
        media = await self._unit_of_work.media.get_with_links(media_id)
        if media is None:
            raise ResourceNotFoundError("Media not found.")
        return media

    async def begin_upload_job(
        self,
        upload_id: UUID,
        *,
        actor_id: UUID,
    ) -> tuple[MediaUploadJob, Media | None, bool]:
        job = await self._unit_of_work.media_upload_jobs.get_by_id(upload_id)
        if job is not None:
            if job.actor_id != actor_id:
                raise ResourceNotFoundError("Media upload not found.")
            if job.status == "PROCESSING":
                return job, None, False
            if job.status == "SUCCEEDED":
                if job.media_id is None:
                    raise RuntimeError("Completed media upload has no media record.")
                return job, await self.get_media(job.media_id), False
            job.status = "PROCESSING"
            job.media_id = None
            await self._unit_of_work.commit()
            return job, None, True

        job = await self._unit_of_work.media_upload_jobs.create(
            MediaUploadJob(
                id=upload_id,
                actor_id=actor_id,
                status="PROCESSING",
            )
        )
        await self._unit_of_work.commit()
        return job, None, True

    async def get_upload_job(
        self,
        upload_id: UUID,
        *,
        actor_id: UUID,
    ) -> tuple[MediaUploadJob, Media | None, Media | None]:
        job = await self._unit_of_work.media_upload_jobs.get_by_id(upload_id)
        if job is None or job.actor_id != actor_id:
            raise ResourceNotFoundError("Media upload not found.")
        media = (
            await self.get_media(job.media_id)
            if job.status == "SUCCEEDED" and job.media_id is not None
            else None
        )
        duplicate_media = None
        if media is not None:
            duplicates = await self._unit_of_work.media.get_by_checksum(
                media.checksum_sha256
            )
            duplicate_media = next(
                (item for item in duplicates if item.id != media.id),
                None,
            )
        return job, media, duplicate_media

    async def fail_upload_job(self, upload_id: UUID) -> None:
        await self._unit_of_work.rollback()
        job = await self._unit_of_work.media_upload_jobs.get_by_id(upload_id)
        if job is None or job.status != "PROCESSING":
            return
        job.status = "FAILED"
        await self._unit_of_work.commit()

    async def upload_media(
        self,
        data: MediaUploadInput,
        *,
        actor_id: UUID,
        upload_job_id: UUID | None = None,
    ) -> tuple[Media, Media | None]:
        staged_path: Path | None = None
        processed_path: Path | None = None
        poster_path: Path | None = None
        storage_key: str | None = None
        committed = False
        maximum_bytes = max(
            self._configuration.media_image_max_bytes,
            self._configuration.media_document_max_bytes,
            self._configuration.media_video_max_bytes,
        )
        try:
            staged_path, _, _ = await asyncio.to_thread(
                self._storage.stage_upload,
                data.source,
                maximum_bytes=maximum_bytes,
            )
            processed = await asyncio.to_thread(
                self._processor.inspect_and_process,
                staged_path,
            )
            processed_path = processed.file_path
            poster_path = processed.poster_path
            kind = MediaKind(processed.kind)
            kind_limit = {
                MediaKind.IMAGE: self._configuration.media_image_max_bytes,
                MediaKind.DOCUMENT: self._configuration.media_document_max_bytes,
                MediaKind.VIDEO: self._configuration.media_video_max_bytes,
            }[kind]
            if processed.size_bytes > kind_limit:
                raise MediaUploadTooLargeError(
                    f"{kind.value.title()} files must be "
                    f"{kind_limit // (1024 * 1024)} MB or smaller."
                )

            media_id = uuid4()
            now = datetime.now(timezone.utc)
            storage_key = self._storage.new_storage_key(
                media_id,
                processed.extension,
                year=now.year,
                month=now.month,
            )
            await asyncio.to_thread(
                self._storage.finalize,
                processed_path,
                storage_key,
                content_type=processed.mime_type,
            )
            processed_path = None
            if poster_path is not None:
                await asyncio.to_thread(
                    self._storage.finalize,
                    poster_path,
                    f"{storage_key}.poster.jpg",
                    content_type="image/jpeg",
                )
                poster_path = None

            original_filename = _safe_filename(data.filename)
            duplicates = await self._unit_of_work.media.get_by_checksum(
                processed.checksum_sha256
            )
            media = Media(
                id=media_id,
                kind=kind,
                storage_key=storage_key,
                original_filename=original_filename,
                mime_type=processed.mime_type,
                size_bytes=processed.size_bytes,
                checksum_sha256=processed.checksum_sha256,
                title=_optional_text(data.title),
                alt_text=_optional_text(data.alt_text),
                width=processed.width,
                height=processed.height,
                duration_seconds=processed.duration_seconds,
            )
            try:
                media = await self._unit_of_work.media.create(media)
                media = await self._unit_of_work.media.get_with_links(media.id)
                if media is None:
                    raise RuntimeError("The created media record could not be loaded.")
                await self._unit_of_work.audit_logs.create(
                    AuditLog(
                        user_id=actor_id,
                        action="media.created",
                        entity_type="media",
                        entity_id=media.id,
                        new_values={
                            "kind": kind.value,
                            "mime_type": processed.mime_type,
                            "size_bytes": processed.size_bytes,
                        },
                        status="success",
                    )
                )
                if upload_job_id is not None:
                    upload_job = await self._unit_of_work.media_upload_jobs.get_by_id(
                        upload_job_id
                    )
                    if (
                        upload_job is None
                        or upload_job.actor_id != actor_id
                        or upload_job.status != "PROCESSING"
                    ):
                        raise ResourceNotFoundError("Media upload not found.")
                    upload_job.status = "SUCCEEDED"
                    upload_job.media_id = media.id
                await self._unit_of_work.commit()
                committed = True
            except IntegrityError as exc:
                await self._unit_of_work.rollback()
                raise ConflictError(
                    "The media record conflicts with existing data."
                ) from exc
            except BaseException:
                await self._unit_of_work.rollback()
                raise

            if duplicates:
                logger.info(
                    "Duplicate media checksum detected",
                    extra={
                        "event": "media.duplicate_checksum",
                        "media_id": str(media.id),
                        "duplicate_count": len(duplicates),
                    },
                )
            return media, duplicates[0] if duplicates else None
        except BaseException:
            if storage_key is not None and not committed:
                await self._cleanup_storage(storage_key)
            raise
        finally:
            for path in (staged_path, processed_path, poster_path):
                if path is not None:
                    await asyncio.to_thread(self._storage.discard, path)

    async def update_media(
        self,
        media_id: UUID,
        data: MediaUpdateInput,
        *,
        actor_id: UUID,
    ) -> Media:
        if not data.fields_set:
            raise MediaValidationError("Provide at least one field to update.")
        media = await self.get_media(media_id)
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}
        try:
            for field in ("title", "alt_text"):
                if field not in data.fields_set:
                    continue
                value = _optional_text(getattr(data, field))
                if (
                    field == "alt_text"
                    and media.kind == MediaKind.IMAGE
                    and value is None
                ):
                    usages = await self._unit_of_work.project_media.list_by_media(
                        media_id
                    )
                    if any(
                        usage.project.status == ProjectStatus.PUBLISHED
                        for usage in usages
                    ):
                        raise ConflictError(
                            "An image used by published content must have alt text."
                        )
                old_value = getattr(media, field)
                if old_value != value:
                    old_values[field] = old_value
                    new_values[field] = value
                    setattr(media, field, value)

            if "links" in data.fields_set:
                links = data.links or ()
                urls = [link.url for link in links]
                if len(urls) != len(set(urls)):
                    raise ConflictError("Each external link URL must be unique.")
                old_links = await self._unit_of_work.media_links.list_by_media_id(
                    media_id
                )
                old_link_values = [
                    {
                        "url": link.url,
                        "label": link.label,
                        "display_order": link.display_order,
                    }
                    for link in old_links
                ]
                new_link_values = [
                    {
                        "url": link.url,
                        "label": _optional_text(link.label),
                        "display_order": link.display_order,
                    }
                    for link in links
                ]
                if old_link_values != new_link_values:
                    old_values["links"] = old_link_values
                    new_values["links"] = new_link_values
                    await self._unit_of_work.media_links.delete_by_media_id(media_id)
                    for link in links:
                        await self._unit_of_work.media_links.create(
                            MediaLink(
                                media_id=media_id,
                                url=link.url,
                                label=_optional_text(link.label),
                                display_order=link.display_order,
                            )
                        )

            if not new_values:
                return media
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="media.updated",
                    entity_type="media",
                    entity_id=media.id,
                    old_values=old_values,
                    new_values=new_values,
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "The media update conflicts with an existing external link."
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return await self.get_media(media_id)

    async def list_usages(self, media_id: UUID) -> list[MediaUsageData]:
        await self.get_media(media_id)
        usages = [
            MediaUsageData(
                usage_type="PROJECT",
                project_id=usage.project_id,
                project_title=usage.project.title,
                project_slug=usage.project.slug,
                role=usage.role,
                display_order=usage.display_order,
                caption=usage.caption,
            )
            for usage in await self._unit_of_work.project_media.list_by_media(
                media_id
            )
        ]
        settings = await self._unit_of_work.site_settings.get_singleton()
        if settings is not None:
            setting_fields = (
                ("logo_media_id", "Logo"),
                ("favicon_media_id", "Favicon"),
                ("default_social_image_media_id", "Default social image"),
                ("profile_image_media_id", "Profile image"),
            )
            usages.extend(
                MediaUsageData(
                    usage_type="SITE_SETTINGS",
                    setting=label,
                )
                for field, label in setting_fields
                if getattr(settings, field) == media_id
            )
        return usages

    async def delete_media(
        self,
        media_id: UUID,
        *,
        actor_id: UUID,
    ) -> None:
        media = await self.get_media(media_id)
        try:
            await self._unit_of_work.media.delete(media)
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="media.deleted",
                    entity_type="media",
                    entity_id=media.id,
                    old_values={
                        "kind": getattr(media.kind, "value", media.kind),
                        "mime_type": media.mime_type,
                    },
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "Media used by a project, post, page, or site setting cannot be deleted."
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        await asyncio.to_thread(self._storage.delete, media.storage_key)

    async def get_public_stored_file(
        self,
        media_id: UUID,
    ) -> tuple[Media, Path | str]:
        await self._require_published_usage(media_id)
        media = await self.get_media(media_id)
        if isinstance(self._storage, SupabaseMediaStorage):
            return media, await asyncio.to_thread(
                self._storage.create_signed_url,
                media.storage_key,
                download_filename=(
                    media.original_filename
                    if media.kind == MediaKind.DOCUMENT
                    else None
                ),
            )
        return media, self._get_local_file(media_id, media.storage_key)

    async def get_admin_stored_file(
        self,
        media_id: UUID,
    ) -> tuple[Media, Path | bytes]:
        media = await self.get_media(media_id)
        if isinstance(self._storage, SupabaseMediaStorage):
            return media, await asyncio.to_thread(
                self._storage.download,
                media.storage_key,
            )
        return media, self._get_local_file(media_id, media.storage_key)

    async def get_public_video_poster(self, media_id: UUID) -> Path | str:
        await self._require_published_usage(media_id)
        media = await self.get_media(media_id)
        if media.kind != MediaKind.VIDEO:
            raise ResourceNotFoundError("Video preview image not found.")
        poster_key = f"{media.storage_key}.poster.jpg"
        if isinstance(self._storage, SupabaseMediaStorage):
            return await asyncio.to_thread(
                self._storage.create_signed_url,
                poster_key,
            )
        return self._get_local_file(media_id, poster_key)

    async def get_admin_video_poster(self, media_id: UUID) -> Path | bytes:
        media = await self.get_media(media_id)
        if media.kind != MediaKind.VIDEO:
            raise ResourceNotFoundError("Video preview image not found.")
        poster_key = f"{media.storage_key}.poster.jpg"
        if isinstance(self._storage, SupabaseMediaStorage):
            return await asyncio.to_thread(self._storage.download, poster_key)
        return self._get_local_file(media_id, poster_key)

    def _get_local_file(self, media_id: UUID, storage_key: str) -> Path:
        if not isinstance(self._storage, LocalMediaStorage):
            raise RuntimeError("Local media storage is not configured.")
        path = self._storage.resolve(storage_key)
        if not path.is_file():
            logger.error(
                "Media database row points to a missing file",
                extra={"event": "media.storage_missing", "media_id": str(media_id)},
            )
            raise ResourceNotFoundError("Media file not found.")
        return path

    async def _require_published_usage(self, media_id: UUID) -> None:
        project_usage = await self._unit_of_work.project_media.has_published_usage(
            media_id
        )
        post_usage = await self._unit_of_work.post_media.has_published_usage(media_id)
        if project_usage or post_usage:
            return
        published_page_sections = (
            await self._unit_of_work.page_media.list_published_sections_for_media(
                media_id
            )
        )
        if any(
            media_id in collect_page_media_ids_from_sections(sections)
            for sections in published_page_sections
        ):
            return
        site_settings = await self._unit_of_work.site_settings.get_singleton()
        if site_settings is not None and media_id in {
            site_settings.logo_media_id,
            site_settings.favicon_media_id,
            site_settings.default_social_image_media_id,
            site_settings.profile_image_media_id,
        }:
            return
        raise ResourceNotFoundError("Media file not found.")

    async def _cleanup_storage(self, storage_key: str) -> None:
        try:
            await asyncio.to_thread(self._storage.delete, storage_key)
        except MediaStorageError:
            logger.exception(
                "Unable to clean up media after a failed database operation",
                extra={"storage_key": storage_key},
            )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _safe_filename(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = _SAFE_FILENAME_CHARS.sub("", name).strip()
    return (name or "upload")[:255]


def _sum_video_poster_bytes(
    storage: LocalMediaStorage,
    storage_keys: list[str],
) -> int:
    total = 0
    for storage_key in storage_keys:
        poster_path = storage.resolve(f"{storage_key}.poster.jpg")
        try:
            file_info = poster_path.stat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(file_info.st_mode):
            total += file_info.st_size
    return total


def _get_media_filesystem_usage(media_directory: Path) -> tuple[int, int, int]:
    directory = media_directory
    while not directory.exists():
        parent = directory.parent
        if parent == directory:
            break
        directory = parent
    usage = shutil.disk_usage(directory)
    return usage.total, usage.used, usage.free
