from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.database.models.enums import NavigationLinkType, NavigationMenu


@dataclass(frozen=True)
class NavigationItemData:
    id: UUID
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
    is_visible: bool
    display_order: int = 0


@dataclass(frozen=True)
class NavigationAdminItem:
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


@dataclass(frozen=True)
class NavigationPublicItem:
    id: UUID
    label: str
    link_type: NavigationLinkType
    href: str | None
    content_text: str | None
    children: list["NavigationPublicItem"]
