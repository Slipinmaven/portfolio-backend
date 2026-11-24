import re
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from typing import Annotated, Self

from app.infrastructure.database.models.enums import SiteLinkPlatform

SiteName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
OwnerName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
LinkUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class SiteLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    platform: SiteLinkPlatform
    url: LinkUrl
    label: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=100),
    ] | None = None

    @field_validator("url")
    @classmethod
    def validate_platform_url(cls, value: str, info) -> str:
        platform = info.data.get("platform")
        if platform == SiteLinkPlatform.EMAIL:
            address = value.removeprefix("mailto:")
            if (
                not value.startswith("mailto:")
                or not re.fullmatch(r"[^@\s]+@[^@\s]+", address)
            ):
                raise ValueError("Email links must use mailto:you@example.com.")
            return f"mailto:{address}"

        parsed = urlsplit(value)
        if platform == SiteLinkPlatform.WHATSAPP:
            if (
                parsed.scheme != "https"
                or parsed.netloc.lower() != "wa.me"
                or not re.fullmatch(r"/[1-9]\d{6,14}", parsed.path)
                or parsed.fragment
            ):
                raise ValueError(
                    "WhatsApp links must use https://wa.me/<country-code><number>."
                )
            return value

        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Social links must use a valid https:// URL.")
        return value


class SiteSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_name: SiteName
    tagline: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=200),
    ] | None = None
    owner_name: OwnerName
    role_title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=150),
    ] | None = None
    owner_bio: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=2000),
    ] | None = None
    location: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=120),
    ] | None = None
    availability_note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=200),
    ] | None = None
    language_code: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=10,
            pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
        ),
    ]
    title_template: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    default_description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=300),
    ] | None = None
    logo_media_id: UUID | None = None
    favicon_media_id: UUID | None = None
    default_social_image_media_id: UUID | None = None
    profile_image_media_id: UUID | None = None
    links: list[SiteLinkInput] = Field(default_factory=list, max_length=8)

    @field_validator("title_template")
    @classmethod
    def validate_title_template(cls, value: str) -> str:
        placeholders = re.findall(r"\{([^{}]+)\}", value)
        if (
            "{title}" not in value
            or any(
                placeholder not in {"title", "site_name"}
                for placeholder in placeholders
            )
            or re.search(
                r"\{[^{}]*\}|\{|\}",
                re.sub(r"\{(?:title|site_name)\}", "", value),
            )
        ):
            raise ValueError(
                "The title template must include {title} and may only use "
                "{title} and {site_name}."
            )
        return value

    @model_validator(mode="after")
    def validate_links(self) -> Self:
        link_ids = [link.id for link in self.links if link.id is not None]
        urls = [link.url for link in self.links]
        if len(set(link_ids)) != len(link_ids):
            raise ValueError("A social link may only appear once.")
        if len(set(urls)) != len(urls):
            raise ValueError("Social link URLs must be unique.")
        return self


class SiteLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: SiteLinkPlatform
    url: str
    label: str | None
    display_order: int
    created_at: datetime


class SiteSettingsResponse(BaseModel):
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
    links: list[SiteLinkResponse]
    updated_at: datetime
