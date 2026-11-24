from fastapi import APIRouter, Depends

from app.application.site_settings.dto import (
    SiteLinkData,
    SiteSettingsBundle,
    SiteSettingsUpdateData,
)
from app.application.site_settings.service import SiteSettingsService
from app.infrastructure.database.models.site_link import SiteLink
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.models.user import User
from app.presentation.dependencies.auth import require_admin
from app.presentation.dependencies.services import get_site_settings_service
from app.presentation.schemas.site_settings import (
    SiteLinkResponse,
    SiteSettingsResponse,
    SiteSettingsUpdateRequest,
)

router = APIRouter(prefix="/site-settings", tags=["site-settings"])


@router.get("/public", response_model=SiteSettingsResponse)
async def get_public_site_settings(
    site_settings_service: SiteSettingsService = Depends(
        get_site_settings_service
    ),
) -> SiteSettingsResponse:
    return _response(await site_settings_service.get_settings())


@router.get("/admin", response_model=SiteSettingsResponse)
async def get_site_settings_for_management(
    _admin: User = Depends(require_admin),
    site_settings_service: SiteSettingsService = Depends(
        get_site_settings_service
    ),
) -> SiteSettingsResponse:
    return _response(await site_settings_service.get_settings())


@router.put("/admin", response_model=SiteSettingsResponse)
async def update_site_settings(
    request: SiteSettingsUpdateRequest,
    admin: User = Depends(require_admin),
    site_settings_service: SiteSettingsService = Depends(
        get_site_settings_service
    ),
) -> SiteSettingsResponse:
    return _response(
        await site_settings_service.update_settings(
            SiteSettingsUpdateData(
                site_name=request.site_name,
                tagline=request.tagline,
                owner_name=request.owner_name,
                role_title=request.role_title,
                owner_bio=request.owner_bio,
                location=request.location,
                availability_note=request.availability_note,
                language_code=request.language_code,
                title_template=request.title_template,
                default_description=request.default_description,
                logo_media_id=request.logo_media_id,
                favicon_media_id=request.favicon_media_id,
                default_social_image_media_id=request.default_social_image_media_id,
                profile_image_media_id=request.profile_image_media_id,
                links=[
                    SiteLinkData(
                        id=link.id,
                        platform=link.platform,
                        url=link.url,
                        label=link.label,
                    )
                    for link in request.links
                ],
            ),
            actor_id=admin.id,
        )
    )


def _response(bundle: SiteSettingsBundle) -> SiteSettingsResponse:
    settings: SiteSettings = bundle.settings
    links: list[SiteLink] = bundle.links
    return SiteSettingsResponse(
        site_name=settings.site_name,
        tagline=settings.tagline,
        owner_name=settings.owner_name,
        role_title=settings.role_title,
        owner_bio=settings.owner_bio,
        location=settings.location,
        availability_note=settings.availability_note,
        language_code=settings.language_code,
        title_template=settings.title_template,
        default_description=settings.default_description,
        logo_media_id=settings.logo_media_id,
        favicon_media_id=settings.favicon_media_id,
        default_social_image_media_id=settings.default_social_image_media_id,
        profile_image_media_id=settings.profile_image_media_id,
        links=[SiteLinkResponse.model_validate(link) for link in links],
        updated_at=settings.updated_at,
    )
