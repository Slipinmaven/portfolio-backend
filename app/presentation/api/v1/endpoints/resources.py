from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.application.posts.markdown import render_markdown
from app.application.resources.dto import (
    ResourceCreateData,
    ResourceListFilters,
    ResourceUpdateData,
)
from app.application.resources.service import ResourceService
from app.infrastructure.database.models.enums import (
    ResourceStatus,
    ResourceType,
)
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_editor_or_admin
from app.presentation.dependencies.services import get_resource_service
from app.presentation.schemas.resources import (
    PublicResourceListResponse,
    PublicResourceResponse,
    ResourceAdminListResponse,
    ResourceAdminResponse,
    ResourceCreateRequest,
    ResourceUpdateRequest,
)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post(
    "",
    response_model=ResourceAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resource(
    request: ResourceCreateRequest,
    editor: User = Depends(require_editor_or_admin),
    resource_service: ResourceService = Depends(get_resource_service),
) -> ResourceAdminResponse:
    resource = await resource_service.create_resource(
        ResourceCreateData(
            title=request.title,
            url=request.url,
            resource_type=request.resource_type,
            creator=request.creator,
            summary=request.summary,
            commentary=request.commentary,
        ),
        actor_id=editor.id,
    )
    return ResourceAdminResponse.model_validate(resource)


@router.get("/admin", response_model=ResourceAdminListResponse)
async def list_resources_for_management(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    resource_type: ResourceType | None = None,
    resource_status: ResourceStatus | None = Query(default=None, alias="status"),
    _editor: User = Depends(require_editor_or_admin),
    resource_service: ResourceService = Depends(get_resource_service),
) -> ResourceAdminListResponse:
    resources, total = await resource_service.list_resources(
        ResourceListFilters(
            offset=offset,
            limit=limit,
            status=resource_status,
            resource_type=resource_type,
        )
    )
    return ResourceAdminListResponse(
        resources=[ResourceAdminResponse.model_validate(item) for item in resources],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/admin/{resource_id}",
    response_model=ResourceAdminResponse,
)
async def get_resource_for_management(
    resource_id: UUID,
    _editor: User = Depends(require_editor_or_admin),
    resource_service: ResourceService = Depends(get_resource_service),
) -> ResourceAdminResponse:
    return ResourceAdminResponse.model_validate(
        await resource_service.get_resource(resource_id)
    )


@router.patch(
    "/admin/{resource_id}",
    response_model=ResourceAdminResponse,
)
async def update_resource(
    resource_id: UUID,
    request: ResourceUpdateRequest,
    editor: User = Depends(require_editor_or_admin),
    resource_service: ResourceService = Depends(get_resource_service),
) -> ResourceAdminResponse:
    resource = await resource_service.update_resource(
        resource_id,
        ResourceUpdateData(
            title=request.title,
            url=request.url,
            resource_type=request.resource_type,
            creator=request.creator,
            summary=request.summary,
            commentary=request.commentary,
            status=request.status,
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=editor.id,
    )
    return ResourceAdminResponse.model_validate(resource)


@router.delete(
    "/admin/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_resource(
    resource_id: UUID,
    editor: User = Depends(require_editor_or_admin),
    resource_service: ResourceService = Depends(get_resource_service),
) -> Response:
    await resource_service.delete_resource(resource_id, actor_id=editor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=PublicResourceListResponse)
async def list_published_resources(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    resource_type: ResourceType | None = None,
    resource_service: ResourceService = Depends(get_resource_service),
) -> PublicResourceListResponse:
    resources, total = await resource_service.list_resources(
        ResourceListFilters(
            offset=offset,
            limit=limit,
            resource_type=resource_type,
            published_only=True,
        )
    )
    return PublicResourceListResponse(
        resources=[_public_response(resource) for resource in resources],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{resource_id}", response_model=PublicResourceResponse)
async def get_published_resource(
    resource_id: UUID,
    resource_service: ResourceService = Depends(get_resource_service),
) -> PublicResourceResponse:
    resource = await resource_service.get_published_resource(resource_id)
    return _public_response(resource)


def _public_response(resource: Resource) -> PublicResourceResponse:
    return PublicResourceResponse(
        **ResourceAdminResponse.model_validate(resource).model_dump(),
        commentary_html=render_markdown(resource.commentary or ""),
    )
