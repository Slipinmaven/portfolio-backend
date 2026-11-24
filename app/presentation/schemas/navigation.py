from __future__ import annotations

import re
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.infrastructure.database.models.enums import NavigationLinkType, NavigationMenu

NavigationLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
RouteKey = Literal["PROJECTS", "ARTICLES", "NOTES", "RESOURCES"]
CustomTarget = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
FooterText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class NavigationItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    parent_id: UUID | None = None
    label: NavigationLabel
    link_type: NavigationLinkType
    page_id: UUID | None = None
    project_id: UUID | None = None
    post_id: UUID | None = None
    category_id: UUID | None = None
    route_key: RouteKey | None = None
    custom_target: CustomTarget | None = None
    content_text: FooterText | None = None
    is_visible: bool = True

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        targets = {
            "PAGE": self.page_id,
            "PROJECT": self.project_id,
            "POST": self.post_id,
            "CATEGORY": self.category_id,
            "ROUTE": self.route_key,
            "EXTERNAL": self.custom_target,
            "EMAIL": self.custom_target,
            "PHONE": self.custom_target,
            "TEXT": self.content_text,
        }
        expected = targets.get(self.link_type.value)
        populated = [
            value
            for value in (
                self.page_id,
                self.project_id,
                self.post_id,
                self.category_id,
                self.route_key,
                self.custom_target,
                self.content_text,
            )
            if value is not None
        ]
        if self.link_type == NavigationLinkType.NONE:
            if populated:
                raise ValueError("Dropdown headings cannot have a destination.")
        elif expected is None or len(populated) != 1:
            raise ValueError("Choose exactly one destination matching the link type.")
        if self.link_type == NavigationLinkType.EXTERNAL:
            parsed = urlsplit(self.custom_target or "")
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("External footer links must use a valid https:// URL.")
        elif self.link_type == NavigationLinkType.EMAIL:
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.custom_target or ""):
                raise ValueError("Enter a valid email address.")
        elif self.link_type == NavigationLinkType.PHONE:
            phone = self.custom_target or ""
            digits = re.sub(r"\D", "", phone)
            if (
                not re.fullmatch(r"\+?[0-9][0-9 ().-]{5,24}", phone)
                or not 7 <= len(digits) <= 15
            ):
                raise ValueError("Enter a valid phone number.")
        return self


class NavigationMenuUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NavigationItemInput] = Field(default_factory=list)


class NavigationAdminItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    menu: NavigationMenu
    parent_id: UUID | None
    label: str
    link_type: NavigationLinkType
    page_id: UUID | None
    project_id: UUID | None
    post_id: UUID | None
    category_id: UUID | None
    route_key: str | None
    custom_target: str | None
    content_text: str | None
    display_order: int
    is_visible: bool
    target_label: str | None
    target_href: str | None
    target_status: str | None
    target_is_eligible: bool
    visibility_reason: str | None


class NavigationPublicItemResponse(BaseModel):
    id: UUID
    label: str
    link_type: NavigationLinkType
    href: str | None
    content_text: str | None
    children: list["NavigationPublicItemResponse"]


class NavigationAdminMenusResponse(BaseModel):
    menus: dict[NavigationMenu, list[NavigationAdminItemResponse]]


class NavigationPublicMenusResponse(BaseModel):
    menus: dict[NavigationMenu, list[NavigationPublicItemResponse]]
