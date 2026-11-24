import unittest
from pathlib import Path

from pydantic import ValidationError

from app.core.config import BACKEND_DIR, Settings


class SettingsTests(unittest.TestCase):
    def test_normalizes_log_level_and_comma_separated_origins(self) -> None:
        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            log_level="debug",
            cors_origins="https://example.test, https://admin.example.test",
        )

        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(
            settings.cors_origins,
            ["https://example.test", "https://admin.example.test"],
        )

    def test_rejects_invalid_log_level(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                log_level="verbose",
            )

    def test_rejects_synchronous_database_driver(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                database_url="postgresql://user:pass@localhost/db",
            )

    def test_resolves_relative_media_directory_from_backend_root(self) -> None:
        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            media_directory=Path("media"),
        )

        self.assertEqual(settings.media_directory, BACKEND_DIR / "media")

    def test_media_storage_warning_threshold_is_bounded(self) -> None:
        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:pass@localhost/db",
        )
        self.assertEqual(settings.media_storage_warning_free_percent, 10)

        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                media_storage_warning_free_percent=0,
            )
