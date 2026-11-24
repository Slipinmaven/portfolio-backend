import json
import logging
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.logging import (
    close_logging,
    configure_logging,
    DateRotatingFileHandler,
    get_application_logger,
    get_error_logger,
    get_security_logger,
)
from app.main import app


def _read_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _read_category_records(directory: Path, prefix: str) -> list[dict[str, object]]:
    return [
        record
        for path in sorted(directory.glob(f"{prefix}-*.log"))
        for record in _read_records(path)
    ]


def _flush_managed_handlers() -> None:
    for handler in logging.getLogger("app").handlers:
        if getattr(handler, "_portfolio_json_handler", False):
            handler.flush()


class JsonLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.log_directory = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        close_logging()

    def test_logs_are_json_and_routed_by_category(self) -> None:
        configure_logging(self.log_directory, level="DEBUG")
        get_application_logger().info(
            "Page request completed",
            extra={"event": "page.request.completed", "status": 200},
        )
        get_security_logger().warning(
            "Login attempt rejected",
            extra={"ip_address": "203.0.113.8"},
        )
        get_security_logger().error("Suspicious login reuse")
        try:
            raise RuntimeError("database unavailable")
        except RuntimeError:
            get_error_logger().exception("Database operation failed")
        _flush_managed_handlers()

        app_records = _read_category_records(self.log_directory / "apps", "application")
        security_records = _read_category_records(self.log_directory / "security", "security")
        error_records = _read_category_records(self.log_directory / "errors", "errors")

        self.assertEqual([record["message"] for record in app_records], ["Page request completed"])
        self.assertEqual(app_records[0]["event"], "page.request.completed")
        self.assertEqual([record["message"] for record in security_records], [
            "Login attempt rejected",
            "Suspicious login reuse",
        ])
        self.assertEqual(security_records[0]["ip_address"], "203.0.113.8")
        self.assertEqual([record["message"] for record in error_records], [
            "Suspicious login reuse",
            "Database operation failed",
        ])
        exception = error_records[1].get("exception")
        if not isinstance(exception, str):
            self.fail("Error log record did not include a formatted exception")
        self.assertIn("RuntimeError: database unavailable", exception)
        self.assertTrue(str(error_records[0]["timestamp"]).endswith("Z"))

    def test_logs_rotate_daily_to_date_stamped_log_files(self) -> None:
        directory = self.log_directory / "apps"
        directory.mkdir()
        stale_file = directory / "application-2000-01-01.log"
        stale_file.write_text("stale", encoding="utf-8")
        today = date(2026, 11, 2)
        tomorrow = today + timedelta(days=1)

        with patch.object(DateRotatingFileHandler, "_today", return_value=today):
            configure_logging(self.log_directory, level=logging.INFO, retention_days=2)
            logging.getLogger("app.test").info("Today")
        with patch.object(DateRotatingFileHandler, "_today", return_value=tomorrow):
            logging.getLogger("app.test").info("Tomorrow")

        today_file = directory / f"application-{today.isoformat()}.log"
        tomorrow_file = directory / f"application-{tomorrow.isoformat()}.log"
        self.assertTrue(today_file.exists())
        self.assertTrue(tomorrow_file.exists())
        self.assertFalse(stale_file.exists())

    def test_configure_logging_is_idempotent(self) -> None:
        configure_logging(self.log_directory)
        app_logger = logging.getLogger("app")
        handler_count = len(app_logger.handlers)
        configure_logging(self.log_directory)
        self.assertEqual(len(app_logger.handlers), handler_count)

    def test_request_middleware_logs_request_id_and_response_metadata(self) -> None:
        with patch(
            "app.main.configure_logging",
            lambda: configure_logging(self.log_directory, level="DEBUG"),
        ):
            with TestClient(app) as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        request_id = response.headers["x-request-id"]
        records = _read_category_records(self.log_directory / "apps", "application")
        record = next(record for record in records if record["event"] == "http.request.completed")
        self.assertEqual(record["request_id"], request_id)
        self.assertEqual(record["event"], "http.request.completed")
        self.assertEqual(record["method"], "GET")
        self.assertEqual(record["path"], "/")
        self.assertEqual(record["status"], 200)
        self.assertIn("duration_ms", record)
