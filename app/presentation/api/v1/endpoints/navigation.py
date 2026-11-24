from fastapi import APIRouter, Depends

from app.application.navigation.dto import NavigationItemData
from app.application.navigation.service import NavigationService
from app.infrastructure.database.models.enums import NavigationMenu
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_admin
from app.presentation.dependencies.services import get_navigation_service
from app.presentation.schemas.navigation import (
    NavigationAdminItemResponse,
    NavigationAdminMenusResponse,
    NavigationMenuUpdateRequest,
    NavigationPublicItemResponse,
    NavigationPublicMenusResponse,
)

router = APIRouter(prefix="/navigation", tags=["navigation"])


@router.get("/public", response_model=NavigationPublicMenusResponse)
async def get_public_navigation(
    navigation_service: NavigationService = Depends(get_navigation_service),
) -> NavigationPublicMenusResponse:
    menus = await navigation_service.list_public_menus()
    return NavigationPublicMenusResponse(
        menus={
            menu: [
                NavigationPublicItemResponse(
                    id=item.id,
                    label=item.label,
                    link_type=item.link_type,
                    href=item.href,
                    content_text=item.content_text,
                    children=[
                        NavigationPublicItemResponse(
                            id=child.id,
                            label=child.label,
                            link_type=child.link_type,
                            href=child.href,
                            content_text=child.content_text,
                            children=[],
                        )
                        for child in item.children
                    ],
                )
                for item in items
            ]
            for menu, items in menus.items()
        }
    )


@router.get("/admin", response_model=NavigationAdminMenusResponse)
async def get_navigation_for_management(
    _admin: User = Depends(require_admin),
    navigation_service: NavigationService = Depends(get_navigation_service),
) -> NavigationAdminMenusResponse:
    menus = await navigation_service.list_admin_menus()
    return NavigationAdminMenusResponse(
        menus={
            menu: [
                NavigationAdminItemResponse.model_validate(item)
                for item in items
            ]
            for menu, items in menus.items()
        }
    )


@router.put(
    "/admin/{menu}",
    response_model=list[NavigationAdminItemResponse],
)
async def update_navigation_menu(
    menu: NavigationMenu,
    request: NavigationMenuUpdateRequest,
    admin: User = Depends(require_admin),
    navigation_service: NavigationService = Depends(get_navigation_service),
) -> list[NavigationAdminItemResponse]:
    items = await navigation_service.update_menu(
        menu,
        [
            NavigationItemData(
                id=item.id,
                parent_id=item.parent_id,
                label=item.label,
                link_type=item.link_type,
                page_id=item.page_id,
                project_id=item.project_id,
                post_id=item.post_id,
                category_id=item.category_id,
                route_key=item.route_key,
                custom_target=item.custom_target,
                content_text=item.content_text,
                is_visible=item.is_visible,
            )
            for item in request.items
        ],
        actor_id=admin.id,
    )
    return [
        NavigationAdminItemResponse.model_validate(item)
        for item in items
    ]
