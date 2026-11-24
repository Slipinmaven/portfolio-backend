import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from PIL import Image, ImageStat

from app.application.errors import (
    ConflictError,
    ResourceNotFoundError,
    MediaStorageError,
    MediaUploadTooLargeError,
    MediaValidationError,
)
from app.application.media.dto import (
    MediaStorageCategory,
    MediaStorageFile,
    MediaStorageSummary,
    MediaUploadInput,
)
from app.application.media.service import MediaService
from app.application.projects.media_dto import ProjectMediaCreateDTO
from app.application.projects.media_service import ProjectMediaService
from app.core.config import Settings, settings
from app.infrastructure.database.models.enums import (
    DevelopmentStatus,
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
)
from app.infrastructure.database.models.media import Media
from app.infrastructure.database.models.media_upload_job import MediaUploadJob
from app.infrastructure.database.models.project import Project
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.unit_of_work.media import MediaUnitOfWork
from app.infrastructure.database.unit_of_work.project import ProjectUnitOfWork
from app.infrastructure.media_processing.processor import (
    MediaProcessor,
    ProcessedMedia,
)
from app.infrastructure.storage.local_media_storage import LocalMediaStorage
from app.infrastructure.storage.supabase_media_storage import SupabaseMediaStorage
from app.main import app
from fastapi.testclient import TestClient
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_media_service
from app.presentation.api.v1.endpoints.media import _media_file_response


class MediaProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.processor = MediaProcessor(
            ffmpeg_binary="ffmpeg",
            ffprobe_binary="ffprobe",
            maximum_video_bytes=50 * 1024 * 1024,
            maximum_video_duration_seconds=60,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_inspects_image_contents_and_dimensions(self) -> None:
        path = self.root / "image.tmp"
        Image.new("RGB", (37, 19), color="blue").save(path, format="PNG")

        result = self.processor.inspect_and_process(path)

        self.assertEqual(result.kind, "IMAGE")
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual((result.width, result.height), (37, 19))
        self.assertEqual(result.file_path, path)
        self.assertEqual(len(result.checksum_sha256), 64)

    def test_inspects_documents_from_file_signature(self) -> None:
        path = self.root / "document.tmp"
        path.write_bytes(b"%PDF-1.7\nnot a full document")

        result = self.processor.inspect_and_process(path)

        self.assertEqual(result.kind, "DOCUMENT")
        self.assertEqual(result.mime_type, "application/pdf")
        self.assertEqual(result.extension, "pdf")

    def test_rejects_unknown_file_signatures_without_a_video_processor(self) -> None:
        path = self.root / "unknown.tmp"
        path.write_bytes(b"not a supported file")
        processor = MediaProcessor(
            ffmpeg_binary="missing-ffmpeg",
            ffprobe_binary="missing-ffprobe",
            maximum_video_bytes=50,
            maximum_video_duration_seconds=60,
        )

        with self.assertRaises(MediaValidationError):
            processor.inspect_and_process(path)

    def test_local_storage_enforces_size_and_rejects_traversal(self) -> None:
        storage = LocalMediaStorage(self.root / "stored")
        with self.assertRaises(MediaUploadTooLargeError):
            storage.stage_upload(io.BytesIO(b"three"), maximum_bytes=2)
        with self.assertRaises(MediaStorageError):
            storage.resolve("../outside")

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "FFmpeg is required for the video processing integration test.",
    )
    def test_poster_skips_leading_black_video_frames(self) -> None:
        source = self.root / "source.mp4"
        staged = self.root / "upload.tmp"
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:r=24:d=1",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=64x64:r=24:d=1",
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[outv]",
                "-map",
                "[outv]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(source),
            ],
            check=True,
            timeout=30,
        )
        source.replace(staged)

        with patch(
            "app.infrastructure.media_processing.processor.subprocess.run",
            wraps=subprocess.run,
        ) as process:
            result = self.processor.inspect_and_process(staged)

        self.assertEqual(result.kind, "VIDEO")
        self.assertEqual(result.mime_type, "video/mp4")
        self.assertGreater(result.duration_seconds or 0, 0)
        self.assertTrue(result.file_path.is_file())
        self.assertIsNotNone(result.poster_path)
        self.assertTrue(result.poster_path and result.poster_path.is_file())
        with Image.open(result.poster_path) as poster:
            brightness = ImageStat.Stat(poster.convert("L")).mean[0]
        self.assertGreater(brightness, 20)
        commands = [call.args[0] for call in process.call_args_list]
        self.assertTrue(
            any(
                "-c:v" in command
                and command[command.index("-c:v") + 1] == "copy"
                for command in commands
            )
        )

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "FFmpeg is required for the video processing integration test.",
    )
    def test_transcodes_non_h264_mp4_to_browser_compatible_video(self) -> None:
        source = self.root / "source.mp4"
        staged = self.root / "upload.tmp"
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:r=24:d=1",
                "-c:v",
                "mpeg4",
                "-q:v",
                "5",
                "-y",
                str(source),
            ],
            check=True,
            timeout=30,
        )
        source.replace(staged)

        result = self.processor.inspect_and_process(staged)
        probe = subprocess.run(
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(result.file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        self.assertEqual(probe.stdout.strip(), "h264")


class MediaResponseTests(unittest.TestCase):
    def test_signed_supabase_media_uses_temporary_redirect(self) -> None:
        media = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            storage_key="2026/11/image.png",
            original_filename="image.png",
            mime_type="image/png",
            size_bytes=5,
            checksum_sha256="a" * 64,
        )

        response = _media_file_response(
            media,
            "https://project.supabase.co/storage/v1/object/sign/asset?token=short-lived",
        )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(
            response.headers["location"],
            "https://project.supabase.co/storage/v1/object/sign/asset?token=short-lived",
        )

    def test_admin_document_bytes_keep_attachment_disposition(self) -> None:
        media = Media(
            id=uuid4(),
            kind=MediaKind.DOCUMENT,
            storage_key="2026/11/report.pdf",
            original_filename="final report.pdf",
            mime_type="application/pdf",
            size_bytes=5,
            checksum_sha256="b" * 64,
        )

        response = _media_file_response(media, b"%PDF-")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"%PDF-")
        self.assertEqual(response.media_type, "application/pdf")
        self.assertIn(
            "attachment; filename*=UTF-8''final%20report.pdf",
            response.headers["content-disposition"],
        )


class MediaServiceUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_supabase_summary_does_not_report_local_disk_quota(self) -> None:
        unit_of_work = _media_unit_of_work()
        unit_of_work.media.get_storage_usage_by_kind = AsyncMock(return_value=[])
        unit_of_work.media.list_video_storage_keys = AsyncMock(return_value=[])
        unit_of_work.media.list_largest_media = AsyncMock(return_value=[])
        configuration = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            media_storage_provider="supabase",
            supabase_url="https://project.supabase.co",
            supabase_secret_key="server-only-test-key",
        )
        service = MediaService(
            cast(MediaUnitOfWork, unit_of_work),
            configuration,
        )

        with patch(
            "app.application.media.service.shutil.disk_usage",
            side_effect=AssertionError("Remote storage must not use local quota."),
        ):
            summary = await service.get_storage_summary()

        self.assertEqual(summary.storage_provider, "supabase")
        self.assertIsNone(summary.filesystem_total_bytes)
        self.assertIsNone(summary.filesystem_free_bytes)
        self.assertIsNone(summary.filesystem_free_percent)
        self.assertFalse(summary.is_low_storage)

    async def test_storage_summary_includes_video_preview_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root = Path(temporary_directory)
            storage_key = "2026/11/video.mp4"
            poster = media_root / "2026" / "11" / "video.mp4.poster.jpg"
            poster.parent.mkdir(parents=True)
            poster.write_bytes(b"poster")

            video = Media(
                id=uuid4(),
                kind=MediaKind.VIDEO,
                storage_key=storage_key,
                original_filename="video.mp4",
                mime_type="video/mp4",
                size_bytes=1200,
                checksum_sha256="d" * 64,
            )
            unit_of_work = _media_unit_of_work()
            unit_of_work.media.get_storage_usage_by_kind = AsyncMock(
                return_value=[
                    (MediaKind.IMAGE, 1, 100),
                    (MediaKind.DOCUMENT, 1, 50),
                    (MediaKind.VIDEO, 1, 1200),
                ]
            )
            unit_of_work.media.list_video_storage_keys = AsyncMock(
                return_value=[storage_key]
            )
            unit_of_work.media.list_largest_media = AsyncMock(
                return_value=[video]
            )
            configuration = settings.model_copy(
                update={
                    "media_directory": media_root,
                    "media_storage_warning_free_percent": 10,
                }
            )
            service = MediaService(
                cast(MediaUnitOfWork, unit_of_work),
                configuration,
            )

            with patch(
                "app.application.media.service.shutil.disk_usage",
                return_value=SimpleNamespace(total=1000, used=950, free=50),
            ):
                summary = await service.get_storage_summary()

        self.assertEqual(summary.item_count, 3)
        self.assertEqual(summary.size_bytes, 1356)
        video_category = next(
            category
            for category in summary.categories
            if category.kind == MediaKind.VIDEO
        )
        self.assertEqual(video_category.item_count, 1)
        self.assertEqual(video_category.size_bytes, 1206)
        self.assertEqual(summary.largest_files[0].original_filename, "video.mp4")
        self.assertEqual(summary.largest_files[0].size_bytes, 1200)
        self.assertEqual(summary.filesystem_total_bytes, 1000)
        self.assertEqual(summary.filesystem_free_bytes, 50)
        self.assertEqual(summary.filesystem_free_percent, 5)
        self.assertEqual(summary.warning_threshold_free_percent, 10)
        self.assertTrue(summary.is_low_storage)
        self.assertEqual(summary.storage_provider, "local")

    async def test_begin_upload_job_persists_processing_state(self) -> None:
        upload_id = uuid4()
        actor_id = uuid4()
        unit_of_work = _media_unit_of_work()
        configuration = settings.model_copy()
        service = MediaService(cast(MediaUnitOfWork, unit_of_work), configuration)

        job, media, should_process = await service.begin_upload_job(
            upload_id,
            actor_id=actor_id,
        )

        self.assertEqual(job.id, upload_id)
        self.assertEqual(job.actor_id, actor_id)
        self.assertEqual(job.status, "PROCESSING")
        self.assertIsNone(media)
        self.assertTrue(should_process)
        unit_of_work.commit.assert_awaited_once()

    async def test_existing_upload_job_is_not_started_twice(self) -> None:
        upload_id = uuid4()
        existing_job = MediaUploadJob(
            id=upload_id,
            actor_id=uuid4(),
            status="PROCESSING",
        )
        unit_of_work = _media_unit_of_work()
        unit_of_work.media_upload_jobs.get_by_id.return_value = existing_job
        service = MediaService(
            cast(MediaUnitOfWork, unit_of_work),
            settings.model_copy(),
        )

        job, media, should_process = await service.begin_upload_job(
            upload_id,
            actor_id=existing_job.actor_id,
        )

        self.assertIs(job, existing_job)
        self.assertIsNone(media)
        self.assertFalse(should_process)
        unit_of_work.commit.assert_not_awaited()

    async def test_upload_job_status_is_scoped_to_its_actor(self) -> None:
        upload_id = uuid4()
        job = MediaUploadJob(
            id=upload_id,
            actor_id=uuid4(),
            status="PROCESSING",
        )
        unit_of_work = _media_unit_of_work()
        unit_of_work.media_upload_jobs.get_by_id.return_value = job
        service = MediaService(
            cast(MediaUnitOfWork, unit_of_work),
            settings.model_copy(),
        )

        with self.assertRaises(ResourceNotFoundError):
            await service.get_upload_job(upload_id, actor_id=uuid4())

    async def test_completed_upload_job_includes_matching_media(self) -> None:
        uploaded = Media(
            id=uuid4(),
            kind=MediaKind.VIDEO,
            storage_key="2026/11/upload.mp4",
            original_filename="upload.mp4",
            mime_type="video/mp4",
            size_bytes=5,
            checksum_sha256="d" * 64,
        )
        existing = Media(
            id=uuid4(),
            kind=MediaKind.VIDEO,
            storage_key="2026/10/existing.mp4",
            original_filename="existing.mp4",
            mime_type="video/mp4",
            size_bytes=5,
            checksum_sha256=uploaded.checksum_sha256,
        )
        job = MediaUploadJob(
            id=uuid4(),
            actor_id=uuid4(),
            status="SUCCEEDED",
            media_id=uploaded.id,
        )
        unit_of_work = _media_unit_of_work(uploaded)
        unit_of_work.media_upload_jobs.get_by_id.return_value = job
        unit_of_work.media.get_by_checksum.return_value = [uploaded, existing]
        service = MediaService(
            cast(MediaUnitOfWork, unit_of_work),
            settings.model_copy(),
        )

        result_job, result_media, duplicate_media = await service.get_upload_job(
            job.id,
            actor_id=job.actor_id,
        )

        self.assertIs(result_job, job)
        self.assertIs(result_media, uploaded)
        self.assertIs(duplicate_media, existing)

    async def test_failed_upload_marks_job_failed(self) -> None:
        job = MediaUploadJob(
            id=uuid4(),
            actor_id=uuid4(),
            status="PROCESSING",
        )
        unit_of_work = _media_unit_of_work()
        unit_of_work.media_upload_jobs.get_by_id.return_value = job
        service = MediaService(
            cast(MediaUnitOfWork, unit_of_work),
            settings.model_copy(),
        )

        await service.fail_upload_job(job.id)

        self.assertEqual(job.status, "FAILED")
        unit_of_work.rollback.assert_awaited_once()
        unit_of_work.commit.assert_awaited_once()

    async def test_upload_stores_processed_bytes_and_commits_media_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_of_work = _media_unit_of_work()
            actor_id = uuid4()
            upload_job = MediaUploadJob(
                id=uuid4(),
                actor_id=actor_id,
                status="PROCESSING",
            )
            unit_of_work.media_upload_jobs.get_by_id.return_value = upload_job
            configuration = settings.model_copy(update={"media_directory": root})

            def inspect(path: Path) -> ProcessedMedia:
                return ProcessedMedia(
                    kind="IMAGE",
                    mime_type="image/png",
                    extension="png",
                    size_bytes=5,
                    checksum_sha256="a" * 64,
                    file_path=path,
                    width=1,
                    height=1,
                )

            with patch(
                "app.application.media.service.MediaProcessor"
            ) as processor_type:
                processor_type.return_value.inspect_and_process.side_effect = inspect
                service = MediaService(
                    cast(MediaUnitOfWork, unit_of_work),
                    configuration,
                )
                media, duplicate_media = await service.upload_media(
                    MediaUploadInput(
                        filename=r"C:\fakepath\cover.png",
                        source=io.BytesIO(b"image"),
                        alt_text="Blue square",
                    ),
                    actor_id=actor_id,
                    upload_job_id=upload_job.id,
                )

            self.assertEqual(media.kind, MediaKind.IMAGE)
            self.assertEqual(media.original_filename, "cover.png")
            self.assertIsNone(duplicate_media)
            self.assertEqual((root / Path(media.storage_key)).read_bytes(), b"image")
            self.assertEqual(upload_job.status, "SUCCEEDED")
            self.assertEqual(upload_job.media_id, media.id)
            unit_of_work.media.get_with_links.assert_awaited_once_with(media.id)
            unit_of_work.commit.assert_awaited_once()
            unit_of_work.audit_logs.create.assert_awaited_once()

    async def test_upload_returns_existing_media_when_checksum_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_of_work = _media_unit_of_work()
            existing_media = Media(
                id=uuid4(),
                kind=MediaKind.IMAGE,
                storage_key="2026/11/existing.png",
                original_filename="existing.png",
                mime_type="image/png",
                size_bytes=5,
                checksum_sha256="c" * 64,
            )
            unit_of_work.media.get_by_checksum.return_value = [existing_media]
            configuration = settings.model_copy(update={"media_directory": root})

            def inspect(path: Path) -> ProcessedMedia:
                return ProcessedMedia(
                    kind="IMAGE",
                    mime_type="image/png",
                    extension="png",
                    size_bytes=5,
                    checksum_sha256="c" * 64,
                    file_path=path,
                    width=1,
                    height=1,
                )

            with patch(
                "app.application.media.service.MediaProcessor"
            ) as processor_type:
                processor_type.return_value.inspect_and_process.side_effect = inspect
                service = MediaService(
                    cast(MediaUnitOfWork, unit_of_work),
                    configuration,
                )
                uploaded_media, duplicate_media = await service.upload_media(
                    MediaUploadInput(
                        filename="copy.png",
                        source=io.BytesIO(b"image"),
                    ),
                    actor_id=uuid4(),
                )

            self.assertNotEqual(uploaded_media.id, existing_media.id)
            self.assertIs(duplicate_media, existing_media)
            unit_of_work.media.get_by_checksum.assert_awaited_once_with("c" * 64)
            unit_of_work.commit.assert_awaited_once()

    async def test_failed_database_commit_removes_the_stored_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_of_work = _media_unit_of_work()
            unit_of_work.commit.side_effect = RuntimeError("database unavailable")
            configuration = settings.model_copy(update={"media_directory": root})

            def inspect(path: Path) -> ProcessedMedia:
                return ProcessedMedia(
                    kind="DOCUMENT",
                    mime_type="application/pdf",
                    extension="pdf",
                    size_bytes=5,
                    checksum_sha256="b" * 64,
                    file_path=path,
                )

            with patch(
                "app.application.media.service.MediaProcessor"
            ) as processor_type:
                processor_type.return_value.inspect_and_process.side_effect = inspect
                service = MediaService(
                    cast(MediaUnitOfWork, unit_of_work),
                    configuration,
                )
                with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                    await service.upload_media(
                        MediaUploadInput(
                            filename="report.pdf",
                            source=io.BytesIO(b"%PDF-"),
                        ),
                        actor_id=uuid4(),
                    )

            stored_files = [
                path
                for path in root.rglob("*")
                if path.is_file() and ".staging" not in path.parts
            ]
            self.assertEqual(stored_files, [])
            unit_of_work.rollback.assert_awaited_once()


class MediaDeliveryPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_supabase_public_asset_is_signed_only_after_published_usage(self) -> None:
        media = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            storage_key="2026/11/image.png",
            original_filename="image.png",
            mime_type="image/png",
            size_bytes=5,
            checksum_sha256="a" * 64,
        )
        unit_of_work = _media_unit_of_work(media)
        configuration = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            media_storage_provider="supabase",
            supabase_url="https://project.supabase.co",
            supabase_service_role_key="server-only-test-key",
        )
        service = MediaService(
            cast(MediaUnitOfWork, unit_of_work),
            configuration,
        )

        with patch.object(
            SupabaseMediaStorage,
            "create_signed_url",
            return_value="https://project.supabase.co/signed",
        ) as create_signed_url:
            with self.assertRaises(ResourceNotFoundError):
                await service.get_public_stored_file(media.id)
            create_signed_url.assert_not_called()

            unit_of_work.project_media.has_published_usage.return_value = True
            returned_media, signed_url = await service.get_public_stored_file(
                media.id
            )

        self.assertIs(returned_media, media)
        self.assertEqual(signed_url, "https://project.supabase.co/signed")
        create_signed_url.assert_called_once_with(
            media.storage_key,
            download_filename=None,
        )

    async def test_public_content_and_posters_require_published_project_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_id = uuid4()
            media = Media(
                id=media_id,
                kind=MediaKind.VIDEO,
                storage_key="2026/11/preview.mp4",
                original_filename="preview.mp4",
                mime_type="video/mp4",
                size_bytes=5,
                checksum_sha256="c" * 64,
            )
            video_path = root / media.storage_key
            poster_path = root / f"{media.storage_key}.poster.jpg"
            video_path.parent.mkdir(parents=True)
            video_path.write_bytes(b"video")
            poster_path.write_bytes(b"poster")
            unit_of_work = _media_unit_of_work(media)
            configuration = settings.model_copy(update={"media_directory": root})
            service = MediaService(
                cast(MediaUnitOfWork, unit_of_work),
                configuration,
            )

            with self.assertRaises(ResourceNotFoundError):
                await service.get_public_stored_file(media_id)
            with self.assertRaises(ResourceNotFoundError):
                await service.get_public_video_poster(media_id)

            unit_of_work.project_media.has_published_usage.return_value = True
            public_media, public_video_path = await service.get_public_stored_file(
                media_id
            )
            public_poster_path = await service.get_public_video_poster(media_id)

            self.assertIs(public_media, media)
            self.assertEqual(public_video_path, video_path)
            self.assertEqual(public_poster_path, poster_path)

            private_media, private_video_path = await service.get_admin_stored_file(
                media_id
            )
            private_poster_path = await service.get_admin_video_poster(media_id)
            self.assertIs(private_media, media)
            self.assertEqual(private_video_path, video_path)
            self.assertEqual(private_poster_path, poster_path)

    async def test_published_page_media_is_public_only_when_live_revision_uses_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_id = uuid4()
            media = Media(
                id=media_id,
                kind=MediaKind.IMAGE,
                storage_key="2026/11/page-image.png",
                original_filename="page-image.png",
                mime_type="image/png",
                size_bytes=5,
                checksum_sha256="e" * 64,
            )
            path = root / media.storage_key
            path.parent.mkdir(parents=True)
            path.write_bytes(b"image")
            unit_of_work = _media_unit_of_work(media)
            configuration = settings.model_copy(update={"media_directory": root})
            service = MediaService(
                cast(MediaUnitOfWork, unit_of_work),
                configuration,
            )
            unit_of_work.page_media.list_published_sections_for_media.return_value = [
                [
                    {
                        "id": str(uuid4()),
                        "type": "HERO",
                        "headline": "Live page",
                        "subline": None,
                        "media_id": str(uuid4()),
                        "button": None,
                    }
                ]
            ]

            with self.assertRaises(ResourceNotFoundError):
                await service.get_public_stored_file(media_id)

            unit_of_work.page_media.list_published_sections_for_media.return_value = [
                [
                    {
                        "id": str(uuid4()),
                        "type": "HERO",
                        "headline": "Live page",
                        "subline": None,
                        "media_id": str(media_id),
                        "button": None,
                    }
                ]
            ]
            public_media, public_path = await service.get_public_stored_file(media_id)

            self.assertIs(public_media, media)
            self.assertEqual(public_path, path)

    async def test_site_settings_media_is_public_and_reported_as_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media_id = uuid4()
            media = Media(
                id=media_id,
                kind=MediaKind.IMAGE,
                storage_key="2026/11/profile.png",
                original_filename="profile.png",
                mime_type="image/png",
                size_bytes=5,
                checksum_sha256="f" * 64,
            )
            path = root / media.storage_key
            path.parent.mkdir(parents=True)
            path.write_bytes(b"image")
            unit_of_work = _media_unit_of_work(media)
            unit_of_work.site_settings.get_singleton.return_value = SiteSettings(
                id=1,
                site_name="Portfolio",
                owner_name="Owner",
                profile_image_media_id=media_id,
            )
            configuration = settings.model_copy(update={"media_directory": root})
            service = MediaService(
                cast(MediaUnitOfWork, unit_of_work),
                configuration,
            )

            public_media, public_path = await service.get_public_stored_file(
                media_id
            )
            usages = await service.list_usages(media_id)

            self.assertIs(public_media, media)
            self.assertEqual(public_path, path)
            self.assertEqual(len(usages), 1)
            self.assertEqual(usages[0].usage_type, "SITE_SETTINGS")
            self.assertEqual(usages[0].setting, "Profile image")


class ProjectMediaServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cover_assignment_rejects_non_image_media(self) -> None:
        project = Project(
            id=uuid4(),
            title="Demo",
            slug="demo",
            short_description="Demo",
            development_status=DevelopmentStatus.PLANNING,
            display_order=0,
            status=ProjectStatus.DRAFT,
            is_featured=False,
        )
        unit_of_work = _project_unit_of_work(
            project,
            Media(id=uuid4(), kind=MediaKind.DOCUMENT),
        )
        service = ProjectMediaService(cast(ProjectUnitOfWork, unit_of_work))

        with self.assertRaises(MediaValidationError):
            await service.add_project_media(
                project.id,
                ProjectMediaCreateDTO(
                    media_id=unit_of_work.media.get_with_links.return_value.id,
                    role=ProjectMediaRole.COVER,
                ),
                actor_id=uuid4(),
            )

        unit_of_work.commit.assert_not_awaited()

    async def test_published_project_rejects_image_without_alt_text(self) -> None:
        project = Project(
            id=uuid4(),
            title="Demo",
            slug="demo",
            short_description="Demo",
            development_status=DevelopmentStatus.PLANNING,
            display_order=0,
            status=ProjectStatus.PUBLISHED,
            is_featured=False,
        )
        image = Media(
            id=uuid4(),
            kind=MediaKind.IMAGE,
            alt_text=None,
        )
        unit_of_work = _project_unit_of_work(project, image)
        service = ProjectMediaService(cast(ProjectUnitOfWork, unit_of_work))

        with self.assertRaises(ConflictError):
            await service.add_project_media(
                project.id,
                ProjectMediaCreateDTO(
                    media_id=image.id,
                    role=ProjectMediaRole.GALLERY,
                ),
                actor_id=uuid4(),
            )

        unit_of_work.commit.assert_not_awaited()

    async def test_gallery_rejects_documents(self) -> None:
        project = Project(
            id=uuid4(),
            title="Demo",
            slug="demo",
            short_description="Demo",
            development_status=DevelopmentStatus.PLANNING,
            display_order=0,
            status=ProjectStatus.DRAFT,
            is_featured=False,
        )
        document = Media(id=uuid4(), kind=MediaKind.DOCUMENT)
        unit_of_work = _project_unit_of_work(project, document)
        service = ProjectMediaService(cast(ProjectUnitOfWork, unit_of_work))

        with self.assertRaises(MediaValidationError):
            await service.add_project_media(
                project.id,
                ProjectMediaCreateDTO(
                    media_id=document.id,
                    role=ProjectMediaRole.GALLERY,
                ),
                actor_id=uuid4(),
            )

        unit_of_work.commit.assert_not_awaited()

    async def test_attachments_require_document_media(self) -> None:
        project = Project(
            id=uuid4(),
            title="Demo",
            slug="demo",
            short_description="Demo",
            development_status=DevelopmentStatus.PLANNING,
            display_order=0,
            status=ProjectStatus.DRAFT,
            is_featured=False,
        )
        image = Media(id=uuid4(), kind=MediaKind.IMAGE)
        unit_of_work = _project_unit_of_work(project, image)
        service = ProjectMediaService(cast(ProjectUnitOfWork, unit_of_work))

        with self.assertRaises(MediaValidationError):
            await service.add_project_media(
                project.id,
                ProjectMediaCreateDTO(
                    media_id=image.id,
                    role=ProjectMediaRole.ATTACHMENT,
                ),
                actor_id=uuid4(),
            )

        unit_of_work.commit.assert_not_awaited()

    async def test_inline_role_cannot_be_manually_assigned(self) -> None:
        project = Project(
            id=uuid4(),
            title="Demo",
            slug="demo",
            short_description="Demo",
            development_status=DevelopmentStatus.PLANNING,
            display_order=0,
            status=ProjectStatus.DRAFT,
            is_featured=False,
        )
        unit_of_work = _project_unit_of_work(project, None)
        service = ProjectMediaService(cast(ProjectUnitOfWork, unit_of_work))

        with self.assertRaises(MediaValidationError):
            await service.add_project_media(
                project.id,
                ProjectMediaCreateDTO(
                    media_id=uuid4(),
                    role=ProjectMediaRole.INLINE,
                ),
                actor_id=uuid4(),
            )

        unit_of_work.media.get_with_links.assert_not_awaited()
        unit_of_work.commit.assert_not_awaited()


class MediaRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_media_and_project_media_management_require_authentication(self) -> None:
        project_id = uuid4()
        with TestClient(app) as client:
            media_response = client.get("/api/v1/media/admin")
            storage_usage_response = client.get(
                "/api/v1/media/admin/storage-usage"
            )
            upload_job_response = client.get(
                f"/api/v1/media/admin/upload-jobs/{uuid4()}"
            )
            project_media_response = client.get(
                f"/api/v1/projects/admin/{project_id}/media"
            )
            media_content_response = client.get(
                f"/api/v1/media/admin/{uuid4()}/content"
            )
            media_poster_response = client.get(
                f"/api/v1/media/admin/{uuid4()}/poster"
            )

        self.assertEqual(media_response.status_code, 401)
        self.assertEqual(storage_usage_response.status_code, 401)
        self.assertEqual(upload_job_response.status_code, 401)
        self.assertEqual(project_media_response.status_code, 401)
        self.assertEqual(media_content_response.status_code, 401)
        self.assertEqual(media_poster_response.status_code, 401)

    def test_storage_usage_route_returns_summary_for_authenticated_editor(self) -> None:
        media_id = uuid4()
        media_service = SimpleNamespace(
            get_storage_summary=AsyncMock(
                return_value=MediaStorageSummary(
                    item_count=1,
                    size_bytes=120,
                    categories=(
                        MediaStorageCategory(
                            kind=MediaKind.IMAGE,
                            item_count=1,
                            size_bytes=120,
                        ),
                        MediaStorageCategory(
                            kind=MediaKind.DOCUMENT,
                            item_count=0,
                            size_bytes=0,
                        ),
                        MediaStorageCategory(
                            kind=MediaKind.VIDEO,
                            item_count=0,
                            size_bytes=0,
                        ),
                    ),
                    largest_files=(
                        MediaStorageFile(
                            id=media_id,
                            kind=MediaKind.IMAGE,
                            original_filename="image.png",
                            title="An image",
                            size_bytes=120,
                        ),
                    ),
                    storage_provider="local",
                    filesystem_total_bytes=1000,
                    filesystem_free_bytes=500,
                    filesystem_free_percent=50,
                    warning_threshold_free_percent=10,
                    is_low_storage=False,
                )
            )
        )
        app.dependency_overrides[get_media_service] = lambda: media_service
        app.dependency_overrides[require_editor_or_admin] = lambda: SimpleNamespace(
            id=uuid4()
        )

        with TestClient(app) as client:
            response = client.get("/api/v1/media/admin/storage-usage")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_count"], 1)
        self.assertEqual(response.json()["size_bytes"], 120)
        self.assertEqual(response.json()["categories"][0]["kind"], "IMAGE")
        self.assertEqual(response.json()["largest_files"][0]["id"], str(media_id))
        self.assertEqual(response.json()["is_low_storage"], False)
        media_service.get_storage_summary.assert_awaited_once_with()

    def test_public_file_routes_use_published_usage_checks(self) -> None:
        media_id = uuid4()
        media_service = SimpleNamespace(
            get_public_stored_file=AsyncMock(
                side_effect=ResourceNotFoundError("Media file not found.")
            ),
            get_public_video_poster=AsyncMock(
                side_effect=ResourceNotFoundError("Media file not found.")
            ),
        )
        app.dependency_overrides[get_media_service] = lambda: media_service

        with TestClient(app) as client:
            content_response = client.get(
                f"/api/v1/media/{media_id}/content"
            )
            poster_response = client.get(
                f"/api/v1/media/{media_id}/poster"
            )

        self.assertEqual(content_response.status_code, 404)
        self.assertEqual(poster_response.status_code, 404)
        media_service.get_public_stored_file.assert_awaited_once_with(media_id)
        media_service.get_public_video_poster.assert_awaited_once_with(media_id)


def _media_unit_of_work(media: Media | None = None) -> SimpleNamespace:
    current_media = media

    async def create_media(record: Media) -> Media:
        nonlocal current_media
        current_media = record
        return record

    async def get_media_with_links(media_id: UUID) -> Media | None:
        if current_media is not None and current_media.id == media_id:
            return current_media
        return None

    return SimpleNamespace(
        media=SimpleNamespace(
            get_by_checksum=AsyncMock(return_value=[]),
            create=AsyncMock(side_effect=create_media),
            get_with_links=AsyncMock(side_effect=get_media_with_links),
        ),
        media_links=SimpleNamespace(),
        project_media=SimpleNamespace(
            has_published_usage=AsyncMock(return_value=False),
            list_by_media=AsyncMock(return_value=[]),
        ),
        post_media=SimpleNamespace(
            has_published_usage=AsyncMock(return_value=False),
            list_by_media=AsyncMock(return_value=[]),
        ),
        page_media=SimpleNamespace(
            list_published_sections_for_media=AsyncMock(return_value=[]),
        ),
        site_settings=SimpleNamespace(
            get_singleton=AsyncMock(return_value=None),
        ),
        audit_logs=SimpleNamespace(create=AsyncMock()),
        media_upload_jobs=SimpleNamespace(
            get_by_id=AsyncMock(return_value=None),
            create=AsyncMock(side_effect=lambda job: job),
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


def _project_unit_of_work(
    project: Project,
    media: Media | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        projects=SimpleNamespace(
            get_with_associations_by_id=AsyncMock(return_value=project),
        ),
        media=SimpleNamespace(get_with_links=AsyncMock(return_value=media)),
        project_media=SimpleNamespace(),
        audit_logs=SimpleNamespace(create=AsyncMock()),
        session=SimpleNamespace(add=AsyncMock(), flush=AsyncMock()),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
