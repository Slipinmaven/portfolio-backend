import json
import logging
import math
import re
import shutil
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.application.errors import (
    MediaProcessingTimeoutError,
    MediaProcessorUnavailableError,
    MediaValidationError,
)

logger = logging.getLogger(__name__)

IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
    "GIF": ("image/gif", "gif"),
}
DOCUMENT_SIGNATURES = (
    (b"%PDF-", "application/pdf", "pdf"),
    (b"PK\x03\x04", "application/zip", "zip"),
    (b"PK\x05\x06", "application/zip", "zip"),
    (b"PK\x07\x08", "application/zip", "zip"),
)
VIDEO_FORMATS = {
    "mov",
    "mp4",
    "m4a",
    "3gp",
    "3g2",
    "mj2",
    "matroska",
    "webm",
    "avi",
}
LEADING_BLACK_INTERVAL_PATTERN = re.compile(
    r"black_start:\s*(-?\d+(?:\.\d+)?)\s+black_end:\s*(-?\d+(?:\.\d+)?)"
)


@dataclass(frozen=True)
class ProcessedMedia:
    kind: str
    mime_type: str
    extension: str
    size_bytes: int
    checksum_sha256: str
    file_path: Path
    width: int | None = None
    height: int | None = None
    duration_seconds: int | None = None
    poster_path: Path | None = None


class MediaProcessor:
    def __init__(
        self,
        *,
        ffmpeg_binary: str,
        ffprobe_binary: str,
        maximum_video_bytes: int,
        maximum_video_duration_seconds: int,
        video_processing_timeout_seconds: int = 600,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.maximum_video_bytes = maximum_video_bytes
        self.maximum_video_duration_seconds = maximum_video_duration_seconds
        self.video_processing_timeout_seconds = video_processing_timeout_seconds

    def inspect_and_process(self, path: Path) -> ProcessedMedia:
        try:
            image = self._inspect_image(path)
            if image is not None:
                return image
            document = self._inspect_document(path)
            if document is not None:
                return document
            if not _is_probable_video(path):
                raise MediaValidationError(
                    "Supported uploads are JPEG, PNG, WebP, GIF, PDF, ZIP, MP4, MOV, WebM, and AVI."
                )
            return self._transcode_video(path)
        except MediaValidationError:
            raise
        except (OSError, UnidentifiedImageError) as exc:
            raise MediaValidationError("The uploaded file is invalid or unreadable.") from exc

    @staticmethod
    def _inspect_image(path: Path) -> ProcessedMedia | None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image_format = image.format
                    width, height = image.size
                    image.verify()
        except UnidentifiedImageError:
            return None
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise MediaValidationError(
                "The image dimensions are too large to process safely."
            ) from exc
        if image_format not in IMAGE_FORMATS:
            raise MediaValidationError(
                "Supported images are JPEG, PNG, WebP, and GIF."
            )
        mime_type, extension = IMAGE_FORMATS[image_format]
        size_bytes = path.stat().st_size
        return ProcessedMedia(
            kind="IMAGE",
            mime_type=mime_type,
            extension=extension,
            size_bytes=size_bytes,
            checksum_sha256=_checksum(path),
            file_path=path,
            width=width,
            height=height,
        )

    @staticmethod
    def _inspect_document(path: Path) -> ProcessedMedia | None:
        with path.open("rb") as source:
            header = source.read(8)
        for signature, mime_type, extension in DOCUMENT_SIGNATURES:
            if header.startswith(signature):
                return ProcessedMedia(
                    kind="DOCUMENT",
                    mime_type=mime_type,
                    extension=extension,
                    size_bytes=path.stat().st_size,
                    checksum_sha256=_checksum(path),
                    file_path=path,
                )
        return None

    def _transcode_video(self, path: Path) -> ProcessedMedia:
        ffprobe = shutil.which(self.ffprobe_binary)
        ffmpeg = shutil.which(self.ffmpeg_binary)
        if ffprobe is None or ffmpeg is None:
            raise MediaProcessorUnavailableError()

        try:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-show_entries",
                    (
                        "format=format_name,duration:"
                        "stream=codec_type,codec_name,width,height,pix_fmt"
                    ),
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingTimeoutError() from exc
        except OSError as exc:
            logger.exception("Unable to start ffprobe")
            raise MediaProcessorUnavailableError() from exc
        if probe.returncode != 0:
            raise MediaValidationError(
                "Upload a valid video file with a supported container."
            )
        try:
            metadata = json.loads(probe.stdout)
            format_names = set(metadata["format"]["format_name"].split(","))
            video_stream = next(
                stream
                for stream in metadata["streams"]
                if stream.get("codec_type") == "video"
            )
            audio_streams = [
                stream
                for stream in metadata["streams"]
                if stream.get("codec_type") == "audio"
            ]
            duration = float(metadata["format"]["duration"])
            width = int(video_stream["width"])
            height = int(video_stream["height"])
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MediaValidationError("The uploaded video could not be inspected.") from exc

        if not format_names.intersection(VIDEO_FORMATS):
            raise MediaValidationError("Upload an MP4, MOV, WebM, or AVI video.")
        if not math.isfinite(duration) or duration <= 0:
            raise MediaValidationError("The video duration could not be verified.")
        if duration > self.maximum_video_duration_seconds:
            raise MediaValidationError(
                f"Video previews must be {self.maximum_video_duration_seconds} seconds or shorter."
            )
        if width <= 0 or height <= 0:
            raise MediaValidationError("The video dimensions are invalid.")

        output_path = path.with_suffix(".mp4")
        poster_path = path.with_suffix(".poster.jpg")
        can_remux = (
            bool(format_names.intersection({"mp4", "mov"}))
            and video_stream.get("codec_name") == "h264"
            and video_stream.get("pix_fmt") == "yuv420p"
            and all(stream.get("codec_name") == "aac" for stream in audio_streams)
        )
        try:
            processing_command = [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
            ]
            if can_remux:
                processing_command.extend(["-c:v", "copy", "-c:a", "copy"])
            else:
                processing_command.extend(
                    [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-fs",
                        str(self.maximum_video_bytes),
                    ]
                )
            processing_command.extend(
                [
                    "-movflags",
                    "+faststart",
                    "-f",
                    "mp4",
                    "-y",
                    str(output_path),
                ]
            )
            transcode = subprocess.run(
                processing_command,
                capture_output=True,
                text=True,
                timeout=self.video_processing_timeout_seconds,
                check=False,
            )
            if transcode.returncode != 0 or not output_path.is_file():
                raise MediaValidationError("The video could not be transcoded.")

            black_scan = subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    str(output_path),
                    "-t",
                    "10",
                    "-vf",
                    "fps=4,scale=160:-2,blackdetect=d=0.01:pix_th=0.10:pic_th=0.90",
                    "-an",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if black_scan.returncode != 0:
                raise MediaValidationError(
                    "A video preview image could not be generated."
                )
            poster_time = _poster_time_after_leading_black(
                black_scan.stderr,
                duration,
            )
            poster = subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    str(output_path),
                    "-ss",
                    f"{poster_time:.3f}",
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale='min(1280,iw)':-2",
                    "-y",
                    str(poster_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if poster.returncode != 0 or not poster_path.is_file():
                raise MediaValidationError("A video preview image could not be generated.")
            output_size = output_path.stat().st_size
            if output_size == 0 or output_size > self.maximum_video_bytes:
                raise MediaValidationError(
                    "The processed video exceeds the configured size limit."
                )

            return ProcessedMedia(
                kind="VIDEO",
                mime_type="video/mp4",
                extension="mp4",
                size_bytes=output_size,
                checksum_sha256=_checksum(output_path),
                file_path=output_path,
                width=width,
                height=height,
                duration_seconds=max(1, math.ceil(duration)),
                poster_path=poster_path,
            )
        except subprocess.TimeoutExpired as exc:
            self._remove_path(output_path)
            self._remove_path(poster_path)
            raise MediaProcessingTimeoutError() from exc
        except OSError as exc:
            self._remove_path(output_path)
            self._remove_path(poster_path)
            logger.exception("Unable to start ffmpeg")
            raise MediaProcessorUnavailableError() from exc
        except Exception:
            self._remove_path(output_path)
            self._remove_path(poster_path)
            raise
        finally:
            self._remove_path(path)

    @staticmethod
    def _remove_path(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Unable to remove media processing temporary file")


def _checksum(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _poster_time_after_leading_black(
    black_scan_output: str,
    duration: float,
) -> float:
    match = LEADING_BLACK_INTERVAL_PATTERN.search(black_scan_output)
    if match is None or float(match.group(1)) > 0.1:
        return 0.0

    black_end = float(match.group(2))
    return min(black_end + 0.05, max(duration - 0.05, 0.0))


def _is_probable_video(path: Path) -> bool:
    with path.open("rb") as source:
        header = source.read(12)
    return (
        header[4:8] == b"ftyp"
        or header.startswith(b"\x1a\x45\xdf\xa3")
        or (header.startswith(b"RIFF") and header[8:12] == b"AVI ")
    )
