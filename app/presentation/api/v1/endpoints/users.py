from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.config import settings
from app.application.users.dto import CreateEditorData, UpdateUserData
from app.application.users.service import UserService
from app.presentation.auth_cookies import (
    AUTH_COOKIE_PATH,
    REFRESH_COOKIE,
    TRUSTED_DEVICE_COOKIE,
)
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import get_current_user, require_admin
from app.presentation.dependencies.services import get_user_service
from app.presentation.schemas.auth import (
    CreateEditorRequest,
    CurrentUserResponse,
    UpdateUserRequest,
    UserListResponse,
)

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


def _update_data(request: UpdateUserRequest) -> UpdateUserData:
    return UpdateUserData(
        email=str(request.email) if request.email is not None else None,
        password=(
            request.password.get_secret_value()
            if request.password is not None
            else None
        ),
        first_name=request.first_name,
        last_name=request.last_name,
    )


@router.get(
    path="",
    response_model=UserListResponse,
)
async def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _admin: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> UserListResponse:
    users, total = await user_service.list_users(offset=offset, limit=limit)
    return UserListResponse(
        users=[CurrentUserResponse.model_validate(user) for user in users],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    path="",
    status_code=status.HTTP_201_CREATED,
    response_model=CurrentUserResponse,
)
async def create_editor(
    request: CreateEditorRequest,
    admin: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> CurrentUserResponse:
    user = await user_service.create_editor(
        CreateEditorData(
            email=str(request.email),
            password=request.password.get_secret_value(),
            first_name=request.first_name,
            last_name=request.last_name,
            created_by_admin_id=str(admin.id),
        )
    )
    return CurrentUserResponse.model_validate(user)


@router.patch(
    path="/me",
    response_model=CurrentUserResponse,
)
async def update_my_profile(
    request: UpdateUserRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> CurrentUserResponse:
    user = await user_service.update_profile(
        current_user.id,
        _update_data(request),
        actor_id=current_user.id,
    )
    if request.password is not None:
        _clear_session_cookies(response)
    return CurrentUserResponse.model_validate(user)


@router.patch(
    path="/{user_id}",
    response_model=CurrentUserResponse,
)
async def update_editor(
    user_id: UUID,
    request: UpdateUserRequest,
    admin: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> CurrentUserResponse:
    user = await user_service.update_profile(
        user_id,
        _update_data(request),
        actor_id=admin.id,
        editor_only=True,
    )
    return CurrentUserResponse.model_validate(user)


def _clear_session_cookies(response: Response) -> None:
    secure = settings.environment == "production"
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=AUTH_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=TRUSTED_DEVICE_COOKIE,
        path=AUTH_COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


@router.delete(
    path="/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_editor(
    user_id: UUID,
    admin: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> None:
    await user_service.delete_editor(user_id, actor_id=admin.id)
