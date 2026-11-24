from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoginData:
    email: str
    password: str = field(repr=False)
    trusted_device: bool = False
    client_ip: str | None = None
    user_agent: str | None = None
    trusted_device_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class AuthTokens:
    user_id: str
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    access_expires_in: int
    refresh_max_age: int
    trusted_device_token: str | None = field(default=None, repr=False)
    trusted_device_max_age: int | None = None
