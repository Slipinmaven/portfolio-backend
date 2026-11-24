from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.application.auth.dto import LoginData
from app.application.auth.service import AuthService
from app.application.errors import AuthenticationError, AuthorizationError
from app.core.config import settings
from app.infrastructure.database.models.user import User
from app.presentation.auth_cookies import (
    AUTH_COOKIE_PATH,
    REFRESH_COOKIE,
    TRUSTED_DEVICE_COOKIE,
)
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.services import get_auth_service
from app.presentation.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    SessionListResponse,
    SessionSummary,
    TrustedDeviceListResponse,
    TrustedDeviceSummary,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.get(
    path="/me",
    response_model=CurrentUserResponse,
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)


def _set_auth_cookies(
    response: Response,
    *,
    refresh_token: str,
    refresh_max_age: int,
    trusted_device_token: str | None = None,
    trusted_device_max_age: int | None = None,
    clear_trusted_device: bool = False,
) -> None:
    secure = settings.environment == "production"
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=AUTH_COOKIE_PATH,
    )
    if trusted_device_token is not None and trusted_device_max_age is not None:
        response.set_cookie(
            key=TRUSTED_DEVICE_COOKIE,
            value=trusted_device_token,
            max_age=trusted_device_max_age,
            httponly=True,
            secure=secure,
            samesite="strict",
            path=AUTH_COOKIE_PATH,
        )
    elif clear_trusted_device:
        response.delete_cookie(
            key=TRUSTED_DEVICE_COOKIE,
            path=AUTH_COOKIE_PATH,
            secure=secure,
            httponly=True,
            samesite="strict",
        )


def _normalized_origin(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _require_trusted_origin(request: Request) -> None:
    origin = _normalized_origin(request.headers.get("origin"))
    allowed_origins = {
        normalized
        for configured in settings.cors_origins
        if (normalized := _normalized_origin(configured)) is not None
    }
    request_origin = _normalized_origin(str(request.base_url))
    if request_origin is not None:
        allowed_origins.add(request_origin)
    if origin is None or origin not in allowed_origins:
        raise AuthorizationError("Request origin is not allowed.")


def _clear_refresh_cookie(response: Response) -> None:
    secure = settings.environment == "production"
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=AUTH_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="lax",
    )


@router.post(
    path="/login",
    status_code=status.HTTP_200_OK,
    response_model=LoginResponse,
)
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    _require_trusted_origin(http_request)
    client_ip = http_request.client.host if http_request.client is not None else None
    tokens = await auth_service.login(
        LoginData(
            email=str(request.email),
            password=request.password.get_secret_value(),
            trusted_device=request.trusted_device,
            client_ip=client_ip,
            user_agent=http_request.headers.get("user-agent"),
            trusted_device_token=http_request.cookies.get(TRUSTED_DEVICE_COOKIE),
        )
    )
    _set_auth_cookies(
        response,
        refresh_token=tokens.refresh_token,
        refresh_max_age=tokens.refresh_max_age,
        trusted_device_token=tokens.trusted_device_token,
        trusted_device_max_age=tokens.trusted_device_max_age,
        clear_trusted_device=True,
    )
    return LoginResponse(
        user_id=tokens.user_id,
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.post(
    path="/refresh",
    status_code=status.HTTP_200_OK,
    response_model=LoginResponse,
)
async def refresh(
    http_request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    _require_trusted_origin(http_request)
    refresh_token = http_request.cookies.get(REFRESH_COOKIE)
    if refresh_token is None:
        raise AuthenticationError("Refresh token is missing or expired.")

    tokens = await auth_service.refresh(refresh_token)
    _set_auth_cookies(
        response,
        refresh_token=tokens.refresh_token,
        refresh_max_age=tokens.refresh_max_age,
    )
    return LoginResponse(
        user_id=tokens.user_id,
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
    )


@router.post(
    path="/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    http_request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    _require_trusted_origin(http_request)
    await auth_service.logout(http_request.cookies.get(REFRESH_COOKIE))
    _clear_refresh_cookie(response)


@router.get(
    path="/sessions",
    response_model=SessionListResponse,
)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> SessionListResponse:
    sessions = await auth_service.list_sessions(current_user.id)
    return SessionListResponse(
        sessions=[SessionSummary.model_validate(session) for session in sessions]
    )


@router.delete(
    path="/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_session(
    session_id: UUID,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    refresh_cookie = http_request.cookies.get(REFRESH_COOKIE)
    refresh_matches = await auth_service.revoke_session(
        current_user.id,
        session_id,
        presented_refresh_token=refresh_cookie,
    )
    if refresh_matches:
        response.delete_cookie(
            key=REFRESH_COOKIE,
            path=AUTH_COOKIE_PATH,
            secure=settings.environment == "production",
            httponly=True,
            samesite="lax",
        )


@router.get(
    path="/devices",
    response_model=TrustedDeviceListResponse,
)
async def list_trusted_devices(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> TrustedDeviceListResponse:
    devices = await auth_service.list_trusted_devices(current_user.id)
    return TrustedDeviceListResponse(
        devices=[
            TrustedDeviceSummary.model_validate(device) for device in devices
        ]
    )


@router.delete(
    path="/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_trusted_device(
    device_id: UUID,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    token_matches_cookie = await auth_service.revoke_trusted_device(
        current_user.id,
        device_id,
        presented_token=http_request.cookies.get(TRUSTED_DEVICE_COOKIE),
    )
    if token_matches_cookie:
        response.delete_cookie(
            key=TRUSTED_DEVICE_COOKIE,
            path=AUTH_COOKIE_PATH,
            secure=settings.environment == "production",
            httponly=True,
            samesite="strict",
        )