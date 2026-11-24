from collections.abc import Awaitable, Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.errors import AuthenticationError, AuthorizationError
from app.application.auth.service import AuthService
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.services import get_auth_service

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise AuthenticationError("Access token is missing or expired.")
    return await auth_service.authenticate_access_token(credentials.credentials)


def require_roles(
    *allowed_roles: UserRole,
) -> Callable[..., Awaitable[User]]:
    async def role_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = getattr(current_user.role, "value", current_user.role)
        if user_role not in {role.value for role in allowed_roles}:
            raise AuthorizationError()
        return current_user

    return role_dependency


require_admin = require_roles(UserRole.ADMIN)
require_editor_or_admin = require_roles(UserRole.EDITOR, UserRole.ADMIN)
