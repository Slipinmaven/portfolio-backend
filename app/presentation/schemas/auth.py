from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)


class LoginResponse(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trusted_device_id: UUID | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None

    @field_validator("ip_address", mode="before")
    @classmethod
    def serialize_ip_address(cls, value: object) -> str | None:
        return str(value) if value is not None else None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class TrustedDeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_name: str | None
    device_type: str | None
    browser: str | None
    operating_system: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None


class TrustedDeviceListResponse(BaseModel):
    devices: list[TrustedDeviceSummary]


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserListResponse(BaseModel):
    users: list[CurrentUserResponse]
    total: int
    offset: int
    limit: int


class CreateEditorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=255)
    first_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    last_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    password: SecretStr | None = Field(default=None, min_length=12, max_length=255)
    first_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] | None = None
    last_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] | None = None

    @model_validator(mode="after")
    def require_nonempty_nonnull_changes(self) -> Self:
        changes = self.model_fields_set
        if not changes:
            raise ValueError("At least one profile field must be provided.")
        if any(getattr(self, field_name) is None for field_name in changes):
            raise ValueError("Profile fields cannot be null.")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=255)
    trusted_device: bool = Field(
        default=False,
        description="Requests that the server remember this device after authentication.",
    )
