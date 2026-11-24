import logging
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx

from app.application.errors import (
    MediaStorageError,
    ResourceNotFoundError,
)
from app.infrastructure.storage.local_media_storage import LocalMediaStorage

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_SIGNED_URL_TTL_SECONDS = 300


class SupabaseMediaStorage:
    def __init__(
        self,
        *,
        staging_root: Path,
        project_url: str,
        api_key: str,
        bucket: str,
        use_legacy_bearer_auth: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._staging = LocalMediaStorage(staging_root)
        self._storage_url = f"{project_url.rstrip('/')}/storage/v1"
        self._api_key = api_key
        self._bucket = bucket
        self._use_legacy_bearer_auth = use_legacy_bearer_auth
        self._transport = transport

    def stage_upload(
        self,
        source: BinaryIO,
        *,
        maximum_bytes: int,
    ) -> tuple[Path, int, str]:
        return self._staging.stage_upload(source, maximum_bytes=maximum_bytes)

    def finalize(
        self,
        staged_path: Path,
        storage_key: str,
        *,
        content_type: str | None = None,
    ) -> None:
        object_url = self._object_url(storage_key)
        headers = self._headers()
        headers.update(
            {
                "cache-control": "max-age=3600",
                "content-type": content_type or "application/octet-stream",
                "x-upsert": "false",
            }
        )
        try:
            size_bytes = staged_path.stat().st_size
            with staged_path.open("rb") as source:
                body: Iterator[bytes] = iter(
                    lambda: source.read(1024 * 1024),
                    b"",
                )
                with self._client() as client:
                    response = client.post(
                        object_url,
                        content=body,
                        headers={
                            **headers,
                            "content-length": str(size_bytes),
                        },
                    )
            self._raise_for_storage_response(response, storage_key)
            staged_path.unlink(missing_ok=True)
        except (httpx.HTTPError, OSError) as exc:
            logger.exception(
                "Unable to upload media to Supabase Storage",
                extra={"storage_key": storage_key},
            )
            raise MediaStorageError() from exc

    def create_signed_url(
        self,
        storage_key: str,
        *,
        download_filename: str | None = None,
    ) -> str:
        object_path = self._encoded_object_path(storage_key)
        sign_url = (
            f"{self._storage_url}/object/sign/"
            f"{quote(self._bucket)}/{object_path}"
        )
        try:
            with self._client() as client:
                response = client.post(
                    sign_url,
                    json={"expiresIn": _SIGNED_URL_TTL_SECONDS},
                    headers=self._headers(),
                )
            self._raise_for_storage_response(
                response,
                storage_key,
                missing_object=True,
            )
            body = response.json()
            signed_path = body.get("signedURL") if isinstance(body, dict) else None
            parsed_signed_path = (
                urlsplit(signed_path) if isinstance(signed_path, str) else None
            )
            if (
                parsed_signed_path is None
                or parsed_signed_path.scheme
                or parsed_signed_path.netloc
                or not parsed_signed_path.path.startswith("/object/sign/")
            ):
                raise ValueError("Supabase returned an invalid signed media URL.")

            query = list(parse_qsl(parsed_signed_path.query, keep_blank_values=True))
            if download_filename is not None:
                query.append(("download", download_filename))
            storage_url = urlsplit(self._storage_url)
            return urlunsplit(
                (
                    storage_url.scheme,
                    storage_url.netloc,
                    f"{storage_url.path}{parsed_signed_path.path}",
                    urlencode(query),
                    "",
                )
            )
        except ResourceNotFoundError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.exception(
                "Unable to create a Supabase media URL",
                extra={"storage_key": storage_key},
            )
            raise MediaStorageError() from exc

    def download(self, storage_key: str) -> bytes:
        try:
            with self._client() as client:
                response = client.get(
                    self._object_url(storage_key),
                    headers=self._headers(),
                )
            self._raise_for_storage_response(
                response,
                storage_key,
                missing_object=True,
            )
            return response.content
        except ResourceNotFoundError:
            raise
        except httpx.HTTPError as exc:
            logger.exception(
                "Unable to download media from Supabase Storage",
                extra={"storage_key": storage_key},
            )
            raise MediaStorageError() from exc

    def delete(self, storage_key: str) -> None:
        self._encoded_object_path(storage_key)
        try:
            with self._client() as client:
                response = client.request(
                    "DELETE",
                    f"{self._storage_url}/object/{quote(self._bucket)}",
                    json={
                        "prefixes": [
                            storage_key,
                            f"{storage_key}.poster.jpg",
                        ]
                    },
                    headers=self._headers(),
                )
            self._raise_for_storage_response(response, storage_key)
        except httpx.HTTPError as exc:
            logger.exception(
                "Unable to delete media from Supabase Storage",
                extra={"storage_key": storage_key},
            )
            raise MediaStorageError() from exc

    def discard(self, path: Path) -> None:
        self._staging.discard(path)

    @staticmethod
    def new_storage_key(
        media_id: UUID,
        extension: str,
        *,
        year: int,
        month: int,
    ) -> str:
        return LocalMediaStorage.new_storage_key(
            media_id,
            extension,
            year=year,
            month=month,
        )

    def _object_url(self, storage_key: str) -> str:
        return (
            f"{self._storage_url}/object/{quote(self._bucket)}/"
            f"{self._encoded_object_path(storage_key)}"
        )

    @staticmethod
    def _encoded_object_path(storage_key: str) -> str:
        relative = PurePosixPath(storage_key)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or "\\" in storage_key
        ):
            raise MediaStorageError()
        return "/".join(quote(part, safe="") for part in relative.parts)

    def _headers(self) -> dict[str, str]:
        headers = {"apikey": self._api_key}
        if self._use_legacy_bearer_auth:
            headers["authorization"] = f"Bearer {self._api_key}"
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=_REQUEST_TIMEOUT,
            transport=self._transport,
        )

    @staticmethod
    def _raise_for_storage_response(
        response: httpx.Response,
        storage_key: str,
        *,
        missing_object: bool = False,
    ) -> None:
        if response.is_success:
            return
        if missing_object and response.status_code in {400, 404}:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.status_code == 404 or (
                isinstance(body, dict)
                and str(body.get("statusCode")) == "404"
            ):
                raise ResourceNotFoundError("Media file not found.")
        logger.error(
            "Supabase Storage returned an unsuccessful response",
            extra={
                "storage_key": storage_key,
                "status_code": response.status_code,
            },
        )
        raise MediaStorageError()
