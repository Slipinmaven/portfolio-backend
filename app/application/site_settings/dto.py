from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.database.models.enums import SiteLinkPlatform
from app.infrastructure.database.models.site_link import SiteLink
from app.infrastructure.database.models.site_settings import SiteSettings


@dataclass(frozen=True)
class SiteLinkData:
    id: UUID | None
    platform: SiteLinkPlatform
    url: str
    label: str | None


@dataclass(frozen=True)
class SiteSettingsUpdateData:
    site_name: str
    tagline: str | None
    owner_name: str
    role_title: str | None
    owner_bio: str | None
    location: str | None
    availability_note: str | None
    language_code: str
    title_template: str
    default_description: str | None
    logo_media_id: UUID | None
    favicon_media_id: UUID | None
    default_social_image_media_id: UUID | None
    profile_image_media_id: UUID | None
    links: list[SiteLinkData]


@dataclass(frozen=True)
class SiteSettingsBundle:
    settings: SiteSettings
    links: list[SiteLink]
