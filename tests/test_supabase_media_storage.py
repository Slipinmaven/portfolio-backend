import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

import httpx

from app.application.errors import MediaStorageError, ResourceNotFoundError
from app.infrastructure.storage.supabase_media_storage import SupabaseMediaStorage


class SupabaseMediaStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _storage(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        use_legacy_bearer_auth: bool = False,
    ) -> SupabaseMediaStorage:
        return SupabaseMediaStorage(
            staging_root=Path(self.temporary_directory.name),
            project_url="https://project.supabase.co",
            api_key="test-server-key",
            bucket="portfolio-media",
            use_legacy_bearer_auth=use_legacy_bearer_auth,
            transport=httpx.MockTransport(handler),
        )

    def test_finalize_uploads_file_and_removes_local_staging_copy(self) -> None:
        staged_path = Path(self.temporary_directory.name) / "upload.tmp"
        staged_path.write_bytes(b"processed image")
        requests = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"Key": "stored"})

        storage = self._storage(handle)
        storage.finalize(
            staged_path,
            "2026/11/image.png",
            content_type="image/png",
        )

        request = requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.url.path,
            "/storage/v1/object/portfolio-media/2026/11/image.png",
        )
        self.assertEqual(request.headers["content-type"], "image/png")
        self.assertEqual(request.headers["apikey"], "test-server-key")
        self.assertNotIn("authorization", request.headers)
        self.assertEqual(request.read(), b"processed image")
        self.assertFalse(staged_path.exists())

    def test_create_signed_url_encodes_download_filename(self) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                request.url.path,
                "/storage/v1/object/sign/portfolio-media/2026/11/report.pdf",
            )
            self.assertEqual(
                json.loads(request.content),
                {"expiresIn": 300},
            )
            return httpx.Response(
                200,
                json={
                    "signedURL": (
                        "/object/sign/portfolio-media/2026/11/report.pdf"
                        "?token=signed-token"
                    )
                },
            )

        storage = self._storage(handle)

        signed_url = storage.create_signed_url(
            "2026/11/report.pdf",
            download_filename="final report.pdf",
        )

        self.assertEqual(
            signed_url,
            "https://project.supabase.co/storage/v1/object/sign/"
            "portfolio-media/2026/11/report.pdf"
            "?token=signed-token&download=final+report.pdf",
        )

    def test_legacy_service_role_key_uses_bearer_authorization(self) -> None:
        captured_headers: dict[str, str] = {}

        def handle(request: httpx.Request) -> httpx.Response:
            captured_headers.update(request.headers)
            return httpx.Response(
                200,
                json={
                    "signedURL": (
                        "/object/sign/portfolio-media/2026/11/image.png"
                        "?token=signed-token"
                    )
                },
            )

        storage = self._storage(handle, use_legacy_bearer_auth=True)
        storage.create_signed_url("2026/11/image.png")

        self.assertEqual(captured_headers["apikey"], "test-server-key")
        self.assertEqual(
            captured_headers["authorization"],
            "Bearer test-server-key",
        )

    def test_download_rejects_missing_objects(self) -> None:
        storage = self._storage(
            lambda request: httpx.Response(
                400,
                json={"statusCode": "404", "error": "Not Found"},
            )
        )

        with self.assertRaises(ResourceNotFoundError):
            storage.download("2026/11/missing.png")

    def test_storage_errors_are_not_returned_as_success(self) -> None:
        storage = self._storage(
            lambda request: httpx.Response(503, json={"error": "unavailable"})
        )
        staged_path = Path(self.temporary_directory.name) / "upload.tmp"
        staged_path.write_bytes(b"processed image")

        with self.assertRaises(MediaStorageError):
            storage.finalize(
                staged_path,
                "2026/11/image.png",
                content_type="image/png",
            )
