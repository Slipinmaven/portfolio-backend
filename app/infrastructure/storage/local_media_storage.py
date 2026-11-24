import hashlib
import logging
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID

from app.application.errors import (
    MediaStorageError,
    MediaUploadTooLargeError,
    MediaValidationError,
)

logger = logging.getLogger(__name__)


class LocalMediaStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.staging_directory = self.root / ".staging"

    def stage_upload(
        self,
        source: BinaryIO,
        *,
        maximum_bytes: int,
    ) -> tuple[Path, int, str]:
        path: Path | None = None
        try:
            self.staging_directory.mkdir(parents=True, exist_ok=True)
            descriptor, path_value = tempfile.mkstemp(
                prefix="upload-",
                suffix=".tmp",
                dir=self.staging_directory,
            )
            path = Path(path_value)
            size_bytes = 0
            checksum = hashlib.sha256()
            with os.fdopen(descriptor, "wb") as target:
                while chunk := source.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > maximum_bytes:
                        raise MediaUploadTooLargeError(
                            f"File exceeds the {maximum_bytes // (1024 * 1024)} MB upload limit."
                        )
                    checksum.update(chunk)
                    target.write(chunk)
            if size_bytes == 0:
                raise MediaValidationError("The uploaded file is empty.")
            return path, size_bytes, checksum.hexdigest()
        except (MediaUploadTooLargeError, MediaValidationError):
            if path is not None:
                self._remove_path(path)
            raise
        except OSError as exc:
            if path is not None:
                self._remove_path(path)
            logger.exception("Unable to stage uploaded media")
            raise MediaStorageError() from exc

    def finalize(
        self,
        staged_path: Path,
        storage_key: str,
        *,
        content_type: str | None = None,
    ) -> Path:
        destination = self.resolve(storage_key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_path, destination)
        except OSError as exc:
            logger.exception("Unable to persist uploaded media")
            raise MediaStorageError() from exc
        return destination

    def resolve(self, storage_key: str) -> Path:
        relative = PurePosixPath(storage_key)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise MediaStorageError()
        destination = self.root.joinpath(*relative.parts).resolve()
        if destination != self.root and self.root not in destination.parents:
            raise MediaStorageError()
        return destination

    def delete(self, storage_key: str) -> None:
        for path in (
            self.resolve(storage_key),
            self.resolve(f"{storage_key}.poster.jpg"),
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.exception("Unable to remove stored media file")
                raise MediaStorageError() from exc

    def discard(self, path: Path) -> None:
        self._remove_path(path)

    @staticmethod
    def new_storage_key(
        media_id: UUID,
        extension: str,
        *,
        year: int,
        month: int,
    ) -> str:
        return f"{year:04d}/{month:02d}/{media_id}.{extension}"

    @staticmethod
    def _remove_path(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Unable to remove staged or stored media file")


