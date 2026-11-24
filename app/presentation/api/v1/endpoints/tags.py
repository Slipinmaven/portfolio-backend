from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.application.tags.dto import CreateTagData, TagListFilters, UpdateTagData
from app.application.tags.service import TagService
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_admin
from app.presentation.dependencies.services import get_tag_service
from app.presentation.schemas.tags import (
    CreateTagRequest,
    TagListResponse,
    TagResponse,
    UpdateTagRequest,
)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=TagListResponse)
async def list_tags(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    tag_service: TagService = Depends(get_tag_service),
) -> TagListResponse:
    tags, total = await tag_service.list_tags(
        TagListFilters(offset=offset, limit=limit, is_active=True)
    )
    return TagListResponse(
        tags=[TagResponse.model_validate(tag) for tag in tags],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/admin", response_model=TagListResponse)
async def list_tags_for_management(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    is_active: bool | None = None,
    _admin: User = Depends(require_admin),
    tag_service: TagService = Depends(get_tag_service),
) -> TagListResponse:
    tags, total = await tag_service.list_tags(
        TagListFilters(offset=offset, limit=limit, is_active=is_active)
    )
    return TagListResponse(
        tags=[TagResponse.model_validate(tag) for tag in tags],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/admin/{tag_id}", response_model=TagResponse)
async def get_tag_for_management(
    tag_id: UUID,
    _admin: User = Depends(require_admin),
    tag_service: TagService = Depends(get_tag_service),
) -> TagResponse:
    tag = await tag_service.get_tag(tag_id)
    return TagResponse.model_validate(tag)


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    request: CreateTagRequest,
    admin: User = Depends(require_admin),
    tag_service: TagService = Depends(get_tag_service),
) -> TagResponse:
    tag = await tag_service.create_tag(
        CreateTagData(
            name=request.name,
            slug=request.slug,
            description=request.description,
            is_active=request.is_active,
        ),
        actor_id=admin.id,
    )
    return TagResponse.model_validate(tag)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: UUID,
    tag_service: TagService = Depends(get_tag_service),
) -> TagResponse:
    tag = await tag_service.get_active_tag(tag_id)
    return TagResponse.model_validate(tag)


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID,
    request: UpdateTagRequest,
    admin: User = Depends(require_admin),
    tag_service: TagService = Depends(get_tag_service),
) -> TagResponse:
    tag = await tag_service.update_tag(
        tag_id,
        UpdateTagData(
            name=request.name,
            slug=request.slug,
            description=request.description,
            is_active=request.is_active,
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=admin.id,
    )
    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    admin: User = Depends(require_admin),
    tag_service: TagService = Depends(get_tag_service),
) -> Response:
    await tag_service.delete_tag(tag_id, actor_id=admin.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
