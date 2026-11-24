from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.projects.media_dto import (
    ProjectMediaCreateDTO,
    ProjectMediaOrderDTO,
    ProjectMediaUpdateDTO,
)
from app.application.projects.media_service import ProjectMediaService
from app.infrastructure.database.models.enums import ProjectMediaRole
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_project_media_service
from app.presentation.schemas.project_media import (
    ProjectMediaCreateRequest,
    ProjectMediaListResponse,
    ProjectMediaOrderRequest,
    ProjectMediaResponse,
    ProjectMediaUpdateRequest,
    project_media_response,
)

router = APIRouter(prefix="/projects", tags=["project media"])


@router.get(
    "/admin/{project_id}/media",
    response_model=ProjectMediaListResponse,
)
async def list_project_media_for_management(
    project_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    service: ProjectMediaService = Depends(get_project_media_service),
) -> ProjectMediaListResponse:
    associations = await service.list_project_media(project_id)
    return ProjectMediaListResponse(
        media=[project_media_response(item) for item in associations]
    )


@router.post(
    "/admin/{project_id}/media",
    response_model=ProjectMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_project_media(
    project_id: UUID,
    request: ProjectMediaCreateRequest,
    editor: User = Depends(require_editor_or_admin),
    service: ProjectMediaService = Depends(get_project_media_service),
) -> ProjectMediaResponse:
    association = await service.add_project_media(
        project_id,
        ProjectMediaCreateDTO(
            media_id=request.media_id,
            role=request.role,
            display_order=request.display_order,
            caption=request.caption,
        ),
        actor_id=editor.id,
    )
    return project_media_response(association)


@router.patch(
    "/admin/{project_id}/media/order",
    response_model=ProjectMediaListResponse,
)
async def reorder_project_media(
    project_id: UUID,
    request: ProjectMediaOrderRequest,
    editor: User = Depends(require_editor_or_admin),
    service: ProjectMediaService = Depends(get_project_media_service),
) -> ProjectMediaListResponse:
    associations = await service.reorder_project_media(
        project_id,
        ProjectMediaOrderDTO(
            role=request.role,
            media_ids=tuple(request.media_ids),
        ),
        actor_id=editor.id,
    )
    return ProjectMediaListResponse(
        media=[project_media_response(item) for item in associations]
    )


@router.patch(
    "/admin/{project_id}/media/{media_id}/{role}",
    response_model=ProjectMediaResponse,
)
async def update_project_media(
    project_id: UUID,
    media_id: UUID,
    role: ProjectMediaRole,
    request: ProjectMediaUpdateRequest,
    editor: User = Depends(require_editor_or_admin),
    service: ProjectMediaService = Depends(get_project_media_service),
) -> ProjectMediaResponse:
    association = await service.update_project_media(
        project_id,
        media_id,
        role,
        ProjectMediaUpdateDTO(
            display_order=request.display_order,
            caption=request.caption,
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=editor.id,
    )
    return project_media_response(association)


@router.delete(
    "/admin/{project_id}/media/{media_id}/{role}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_project_media(
    project_id: UUID,
    media_id: UUID,
    role: ProjectMediaRole,
    editor: User = Depends(require_editor_or_admin),
    service: ProjectMediaService = Depends(get_project_media_service),
) -> None:
    await service.remove_project_media(
        project_id,
        media_id,
        role,
        actor_id=editor.id,
    )


@router.get(
    "/{slug}/media",
    response_model=ProjectMediaListResponse,
)
async def list_published_project_media(
    slug: str,
    service: ProjectMediaService = Depends(get_project_media_service),
) -> ProjectMediaListResponse:
    associations = await service.list_published_project_media(slug)
    return ProjectMediaListResponse(
        media=[project_media_response(item) for item in associations]
    )
