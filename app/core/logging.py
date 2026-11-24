"""Structured JSON logging with separate daily rotating application, security, and error files."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO, Any

from app.core.config import settings

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
_HANDLER_MARKER = "_portfolio_json_handler"
_previous_logger_state: tuple[int, bool] | None = None


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat(
            timespec="milliseconds"
        )
        payload: dict[str, Any] = {
            "timestamp": timestamp.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", request_id_context.get()),
            "message": record.getMessage(),
        }

        for key in (
            "method",
            "path",
            "status",
            "duration_ms",
            "user_id",
            "created_by_user_id",
            "changed_fields",
            "farm_id",
            "error_code",
            "ip_address",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=str, ensure_ascii=True)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_context.get()
        return True


class _CategoryFilter(logging.Filter):
    def __init__(self, category: str) -> None:
        super().__init__()
        self.category = category

    def filter(self, record: logging.LogRecord) -> bool:
        is_security = record.name == "app.security" or record.name.startswith("app.security.")
        if self.category == "security":
            return is_security
        if self.category == "errors":
            return record.levelno >= logging.ERROR
        return not is_security and record.levelno < logging.ERROR


class DateRotatingFileHandler(logging.Handler):
    terminator = "\n"

    def __init__(
        self,
        directory: Path,
        prefix: str,
        retention_days: int,
        level: int = logging.NOTSET,
    ) -> None:
        super().__init__(level)
        self.directory = directory
        self.prefix = prefix
        self.retention_days = retention_days
        self.directory.mkdir(parents=True, exist_ok=True)
        self._current_date = self._today()
        self._stream: TextIO | None = None
        self._prune_old_logs()

    @staticmethod
    def _today() -> date:
        return datetime.now(timezone.utc).date()

    def _path_for_date(self, file_date: date) -> Path:
        return self.directory / f"{self.prefix}-{file_date.isoformat()}.log"

    def _ensure_current_file(self) -> None:
        today = self._today()
        if today != self._current_date:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self._current_date = today
            self._prune_old_logs()
        if self._stream is None:
            self._stream = self._path_for_date(today).open("a", encoding="utf-8")

    def _prune_old_logs(self) -> None:
        cutoff = self._today() - timedelta(days=self.retention_days)
        for path in self.directory.glob(f"{self.prefix}-*.log"):
            date_text = path.stem.removeprefix(f"{self.prefix}-")
            try:
                file_date = date.fromisoformat(date_text)
            except ValueError:
                continue
            if file_date < cutoff:
                path.unlink(missing_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.acquire()
            try:
                self._ensure_current_file()
                if self._stream is not None:
                    self._stream.write(f"{self.format(record)}{self.terminator}")
                    self._stream.flush()
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self.acquire()
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        finally:
            self.release()
        super().close()


def _resolve_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    resolved = logging.getLevelNamesMapping().get(level.upper())
    if resolved is None:
        raise ValueError(f"Unknown logging level: {level}")
    return resolved


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"app.{name}")


def get_application_logger() -> logging.Logger:
    return get_logger("application")


def get_error_logger() -> logging.Logger:
    return get_logger("error")


def get_security_logger() -> logging.Logger:
    return get_logger("security")


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()


def configure_logging(
    log_directory: Path | None = None,
    *,
    level: int | str | None = None,
    retention_days: int | None = None,
) -> None:
    """Configure daily UTC log rotation and prune backups older than the retention window."""
    global _previous_logger_state

    retention = settings.log_retention_days if retention_days is None else retention_days
    if retention < 0:
        raise ValueError("retention_days cannot be negative")

    app_logger = logging.getLogger("app")
    if _previous_logger_state is None:
        _previous_logger_state = (app_logger.level, app_logger.propagate)
    _remove_managed_handlers(app_logger)

    app_logger.setLevel(_resolve_level(settings.log_level if level is None else level))
    app_logger.propagate = False
    base_directory = log_directory or settings.log_dir
    formatter = StructuredFormatter()
    request_filter = RequestIdFilter()
    categories = {
        "apps": ("apps", "application.log", _CategoryFilter("apps")),
        "security": ("security", "security.log", _CategoryFilter("security")),
        "errors": ("errors", "errors.log", _CategoryFilter("errors")),
    }

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_filter)
    setattr(console_handler, _HANDLER_MARKER, True)
    app_logger.addHandler(console_handler)

    for directory_name, filename, category_filter in categories.values():
        directory = base_directory / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        handler = DateRotatingFileHandler(
            directory,
            Path(filename).stem,
            retention,
        )
        handler.setFormatter(formatter)
        handler.addFilter(request_filter)
        handler.addFilter(category_filter)
        setattr(handler, _HANDLER_MARKER, True)
        app_logger.addHandler(handler)


def close_logging() -> None:
    """Close managed handlers and restore the app logger's original configuration."""
    global _previous_logger_state

    app_logger = logging.getLogger("app")
    _remove_managed_handlers(app_logger)
    if _previous_logger_state is not None:
        app_logger.setLevel(_previous_logger_state[0])
        app_logger.propagate = _previous_logger_state[1]
        _previous_logger_state = None
