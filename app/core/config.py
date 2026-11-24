import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Jasper's Portfolio"
    app_version: str = "1.0.0"
    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    timezone: str = "UTC"
    media_directory: Path = BACKEND_DIR / "media"
    media_storage_provider: Literal["local", "supabase"] = "local"
    supabase_url: str | None = None
    supabase_secret_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_media_bucket: str = "portfolio-media"
    media_storage_warning_free_percent: int = Field(default=10, ge=1, le=99)
    media_image_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    media_document_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    media_video_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    media_video_max_duration_seconds: int = Field(default=60, ge=1)
    media_video_processing_timeout_seconds: int = Field(
        default=600,
        ge=30,
        le=3600,
    )
    media_ffmpeg_binary: str = "ffmpeg"
    media_ffprobe_binary: str = "ffprobe"

    # Database
    database_url: SecretStr = Field(min_length=1)
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_pool_timeout: int = Field(default=30, ge=1, le=300)
    database_pool_recycle: int = Field(default=1800, ge=60, le=86400)
    database_pool_pre_ping: bool = True
    database_echo: bool = False

    # Authentication
    jwt_secret_key: SecretStr = Field(default=SecretStr(""))
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_session_days: int = Field(default=7, ge=1, le=30)
    session_idle_minutes: int = Field(default=60, ge=1, le=1440)
    session_activity_update_seconds: int = Field(default=300, ge=1, le=3600)
    trusted_device_days: int = Field(default=30, ge=1, le=90)
    login_failure_limit: int = Field(default=10, ge=1, le=100)
    login_failure_window_minutes: int = Field(default=15, ge=1, le=1440)

    @property
    def database_connections_per_process(self) -> int:
        return self.database_pool_size + self.database_max_overflow

    # Logging
    log_level: str = "INFO"
    log_dir: Path = BACKEND_DIR / "logs"
    log_retention_days: int = Field(default=30, ge=1, le=3650)

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        return value

    @model_validator(mode="after")
    def validate_media_storage_configuration(self) -> "Settings":
        if self.media_storage_provider != "supabase":
            return self
        if (
            not self.supabase_url
            or not (
                self.supabase_secret_key.get_secret_value().strip()
                or self.supabase_service_role_key.get_secret_value().strip()
            )
        ):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SECRET_KEY (or the legacy "
                "SUPABASE_SERVICE_ROLE_KEY) are required "
                "when MEDIA_STORAGE_PROVIDER=supabase"
            )
        parsed_url = urlsplit(self.supabase_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.path not in ("", "/")
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("SUPABASE_URL must be an HTTPS project URL.")
        if not self.supabase_media_bucket or "/" in self.supabase_media_bucket:
            raise ValueError("SUPABASE_MEDIA_BUCKET must be a bucket name.")
        return self

    @field_validator("media_directory", mode="before")
    @classmethod
    def resolve_media_directory(cls, value: Path | str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else BACKEND_DIR / path

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret and len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def normalize_cors_origins(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
