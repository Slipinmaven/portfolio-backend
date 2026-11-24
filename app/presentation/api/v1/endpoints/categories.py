from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.application.categories.dto import (
    CategoryListFilters,
    CreateCategoryData,
    UpdateCategoryData,
)
from app.application.categories.service import CategoryService
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_admin
from app.presentation.dependencies.services import get_category_service
from app.presentation.schemas.categories import (
    CategoryListResponse,
    CategoryResponse,
    CreateCategoryRequest,
    MoveCategoryRequest,
    UpdateCategoryRequest,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CategoryListResponse)
async def list_categories(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryListResponse:
    categories, total = await category_service.list_categories(
        CategoryListFilters(offset=offset, limit=limit, is_active=True)
    )
    return CategoryListResponse(
        categories=[CategoryResponse.model_validate(category) for category in categories],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/admin", response_model=CategoryListResponse)
async def list_categories_for_management(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    is_active: bool | None = None,
    _admin: User = Depends(require_admin),
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryListResponse:
    categories, total = await category_service.list_categories(
        CategoryListFilters(offset=offset, limit=limit, is_active=is_active)
    )
    return CategoryListResponse(
        categories=[CategoryResponse.model_validate(category) for category in categories],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/slug/{slug}", response_model=CategoryResponse)
async def get_active_category_by_slug(
    slug: str,
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await category_service.get_active_category_by_slug(slug)
    return CategoryResponse.model_validate(category)


@router.get("/admin/{category_id}", response_model=CategoryResponse)
async def get_category_for_management(
    category_id: UUID,
    _admin: User = Depends(require_admin),
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await category_service.get_category(category_id)
    return CategoryResponse.model_validate(category)


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    request: CreateCategoryRequest,
    admin: User = Depends(require_admin),
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await category_service.create_category(
        CreateCategoryData(
            name=request.name,
            slug=request.slug,
            description=request.description,
            parent_id=request.parent_id,
            display_order=request.display_order,
            is_active=request.is_active,
        ),
        actor_id=admin.id,
    )
    return CategoryResponse.model_validate(category)


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: UUID,
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await category_service.get_active_category(category_id)
    return CategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    request: UpdateCategoryRequest,
    admin: User = Depends(require_admin),
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await category_service.update_category(
        category_id,
        UpdateCategoryData(
            name=request.name,
            slug=request.slug,
            description=request.description,
            parent_id=request.parent_id,
            display_order=request.display_order,
            is_active=request.is_active,
            fields_set=frozenset(request.model_fields_set),
        ),
        actor_id=admin.id,
    )
    return CategoryResponse.model_validate(category)


@router.post(
    "/{category_id}/move",
    response_model=CategoryResponse,
)
async def move_category(
    category_id: UUID,
    request: MoveCategoryRequest,
    admin: User = Depends(require_admin),
    category_service: CategoryService = Depends(get_category_service),
) -> CategoryResponse:
    category = await category_service.move_category(
        category_id,
        request.direction,
        actor_id=admin.id,
    )
    return CategoryResponse.model_validate(category)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_category(
    category_id: UUID,
    admin: User = Depends(require_admin),
    category_service: CategoryService = Depends(get_category_service),
) -> Response:
    await category_service.delete_category(category_id, actor_id=admin.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
