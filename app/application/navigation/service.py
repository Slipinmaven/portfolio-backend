from collections import defaultdict
import re
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.navigation.dto import (
    NavigationAdminItem,
    NavigationItemData,
    NavigationPublicItem,
)
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import (
    NavigationLinkType,
    NavigationMenu,
    PageStatus,
    PostStatus,
    ProjectStatus,
)
from app.infrastructure.database.models.navigation_item import NavigationItem
from app.infrastructure.database.unit_of_work.navigation import NavigationUnitOfWork


ROUTE_TARGETS: dict[str, tuple[str, str]] = {
    "PROJECTS": ("Projects", "/projects"),
    "ARTICLES": ("Articles", "/articles"),
    "NOTES": ("Notes", "/notes"),
    "RESOURCES": ("Resources", "/resources"),
}


class NavigationService:
    def __init__(self, unit_of_work: NavigationUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_admin_menus(
        self,
    ) -> dict[NavigationMenu, list[NavigationAdminItem]]:
        return {
            menu: await self._admin_items(await self._unit_of_work.navigation.list_menu(menu))
            for menu in NavigationMenu
        }

    async def list_public_menus(
        self,
    ) -> dict[NavigationMenu, list[NavigationPublicItem]]:
        public_menus: dict[NavigationMenu, list[NavigationPublicItem]] = {}
        for menu in NavigationMenu:
            items = await self._unit_of_work.navigation.list_menu(menu)
            resolved = await self._resolve_items(items)
            public_menus[menu] = _public_tree(resolved)
        return public_menus

    async def update_menu(
        self,
        menu: NavigationMenu,
        items: list[NavigationItemData],
        *,
        actor_id: UUID,
    ) -> list[NavigationAdminItem]:
        normalized = _validate_menu_items(menu, items)
        await self._validate_targets(normalized)
        existing = await self._unit_of_work.navigation.list_menu(menu)
        old_values = _audit_items(existing)
        new_values = _audit_data(normalized, menu)

        if old_values != new_values:
            stored = [
                NavigationItem(
                    id=item.id,
                    menu=menu,
                    parent_id=item.parent_id,
                    label=item.label.strip(),
                    link_type=item.link_type,
                    page_id=item.page_id,
                    project_id=item.project_id,
                    post_id=item.post_id,
                    category_id=item.category_id,
                    route_key=item.route_key,
                    custom_target=item.custom_target,
                    content_text=item.content_text,
                    display_order=item.display_order,
                    is_visible=item.is_visible,
                )
                for item in normalized
            ]
            menu_entity_id = uuid5(NAMESPACE_URL, f"portfolio-navigation:{menu.value}")
            try:
                await self._unit_of_work.navigation.replace_menu(menu, stored)
                await self._unit_of_work.audit_logs.create(
                    AuditLog(
                        user_id=actor_id,
                        action="navigation.menu_updated",
                        entity_type="navigation_menu",
                        entity_id=menu_entity_id,
                        old_values={"menu": menu.value, "items": old_values},
                        new_values={"menu": menu.value, "items": new_values},
                        status="success",
                    )
                )
                await self._unit_of_work.commit()
            except IntegrityError as exc:
                await self._unit_of_work.rollback()
                raise ConflictError(
                    "A navigation target changed while the menu was being saved. "
                    "Refresh and try again.",
                    code="NAVIGATION_TARGET_CONFLICT",
                ) from exc
            except BaseException:
                await self._unit_of_work.rollback()
                raise

        return await self._admin_items(
            await self._unit_of_work.navigation.list_menu(menu)
        )

    async def _validate_targets(self, items: list[NavigationItemData]) -> None:
        page_ids = list(
            dict.fromkeys(item.page_id for item in items if item.page_id is not None)
        )
        project_ids = [
            item.project_id
            for item in items
            if item.project_id is not None
        ]
        project_ids = list(dict.fromkeys(project_ids))
        post_ids = [item.post_id for item in items if item.post_id is not None]
        post_ids = list(dict.fromkeys(post_ids))
        category_ids = [
            item.category_id for item in items if item.category_id is not None
        ]
        category_ids = list(dict.fromkeys(category_ids))
        pages = await self._unit_of_work.pages.get_by_ids(page_ids)
        projects = await self._unit_of_work.projects.get_by_ids(project_ids)
        posts = await self._unit_of_work.posts.get_by_ids(post_ids)
        categories = await self._unit_of_work.categories.get_by_ids(category_ids)
        if len(pages) != len(page_ids):
            raise ResourceNotFoundError("One or more selected pages no longer exist.")
        if len(projects) != len(project_ids):
            raise ResourceNotFoundError(
                "One or more selected projects no longer exist."
            )
        if len(posts) != len(post_ids):
            raise ResourceNotFoundError("One or more selected posts no longer exist.")
        if len(categories) != len(category_ids):
            raise ResourceNotFoundError(
                "One or more selected categories no longer exist."
            )

    async def _admin_items(
        self,
        items: list[NavigationItem],
    ) -> list[NavigationAdminItem]:
        resolved = await self._resolve_items(items)
        children_by_parent: dict[UUID, list[dict[str, object]]] = defaultdict(list)
        for entry in resolved:
            if entry["item"].parent_id is not None:
                children_by_parent[entry["item"].parent_id].append(entry)

        result: list[NavigationAdminItem] = []
        for entry in resolved:
            item: NavigationItem = entry["item"]
            eligible: bool = entry["eligible"]
            reason: str | None = None
            if not item.is_visible:
                reason = "Hidden in this menu."
            elif not eligible:
                reason = entry["reason"]
            elif (
                item.link_type == NavigationLinkType.NONE
                and not any(
                    child["eligible"] and child["item"].is_visible
                    for child in children_by_parent.get(item.id, [])
                )
            ):
                reason = "No visible submenu items."
            elif item.parent_id is not None:
                parent = next(
                    (
                        candidate
                        for candidate in resolved
                        if candidate["item"].id == item.parent_id
                    ),
                    None,
                )
                if parent is None or not parent["item"].is_visible:
                    reason = "Parent heading is hidden."
                elif not parent["eligible"]:
                    reason = "Parent target is unavailable."
            result.append(
                NavigationAdminItem(
                    id=item.id,
                    menu=NavigationMenu(item.menu),
                    parent_id=item.parent_id,
                    label=item.label,
                    link_type=NavigationLinkType(item.link_type),
                    page_id=item.page_id,
                    project_id=item.project_id,
                    post_id=item.post_id,
                    category_id=item.category_id,
                    route_key=item.route_key,
                    custom_target=item.custom_target,
                    content_text=item.content_text,
                    display_order=item.display_order,
                    is_visible=item.is_visible,
                    target_label=entry["target_label"],
                    target_href=entry["href"],
                    target_status=entry["status"],
                    target_is_eligible=eligible,
                    visibility_reason=reason,
                )
            )
        return result

    async def _resolve_items(
        self,
        items: list[NavigationItem],
    ) -> list[dict[str, object]]:
        page_ids = list(
            dict.fromkeys(item.page_id for item in items if item.page_id is not None)
        )
        project_ids = list(
            dict.fromkeys(
                item.project_id for item in items if item.project_id is not None
            )
        )
        post_ids = list(
            dict.fromkeys(item.post_id for item in items if item.post_id is not None)
        )
        category_ids = list(
            dict.fromkeys(
                item.category_id for item in items if item.category_id is not None
            )
        )
        pages = {
            page.id: page for page in await self._unit_of_work.pages.get_by_ids(page_ids)
        }
        projects = {
            project.id: project
            for project in await self._unit_of_work.projects.get_by_ids(project_ids)
        }
        posts = {
            post.id: post for post in await self._unit_of_work.posts.get_by_ids(post_ids)
        }
        categories = {
            category.id: category
            for category in await self._unit_of_work.categories.get_by_ids(category_ids)
        }

        resolved: list[dict[str, object]] = []
        for item in items:
            link_type = NavigationLinkType(item.link_type)
            target_label: str | None = None
            href: str | None = None
            target_status: str | None = None
            eligible = True
            reason: str | None = None
            if link_type == NavigationLinkType.PAGE:
                page = pages.get(item.page_id)
                if page is None:
                    eligible = False
                    reason = "Page no longer exists."
                else:
                    target_label = page.slug
                    href = "/" if page.system_key == "HOME" else f"/{page.slug}"
                    target_status = str(getattr(page.status, "value", page.status))
                    eligible = PageStatus(page.status) == PageStatus.PUBLISHED
                    if not eligible:
                        reason = f"Page is {target_status.lower()}."
            elif link_type == NavigationLinkType.PROJECT:
                project = projects.get(item.project_id)
                if project is None:
                    eligible = False
                    reason = "Project no longer exists."
                else:
                    target_label = project.title
                    href = f"/projects/{project.slug}"
                    target_status = str(
                        getattr(project.status, "value", project.status)
                    )
                    eligible = ProjectStatus(project.status) == ProjectStatus.PUBLISHED
                    if not eligible:
                        reason = f"Project is {target_status.lower()}."
            elif link_type == NavigationLinkType.POST:
                post = posts.get(item.post_id)
                if post is None:
                    eligible = False
                    reason = "Post no longer exists."
                else:
                    kind = str(getattr(post.kind, "value", post.kind)).lower()
                    target_label = post.title
                    href = f"/{kind}s/{post.slug}"
                    target_status = str(getattr(post.status, "value", post.status))
                    eligible = PostStatus(post.status) == PostStatus.PUBLISHED
                    if not eligible:
                        reason = f"Post is {target_status.lower()}."
            elif link_type == NavigationLinkType.CATEGORY:
                category = categories.get(item.category_id)
                if category is None:
                    eligible = False
                    reason = "Category no longer exists."
                else:
                    target_label = category.name
                    href = f"/categories/{category.slug}"
                    target_status = "active" if category.is_active else "inactive"
                    eligible = category.is_active
                    if not eligible:
                        reason = "Category is inactive."
            elif link_type == NavigationLinkType.ROUTE:
                route = ROUTE_TARGETS.get(item.route_key or "")
                if route is None:
                    eligible = False
                    reason = "Listing route is unavailable."
                else:
                    target_label, href = route
            elif link_type == NavigationLinkType.EXTERNAL:
                href = item.custom_target
            elif link_type == NavigationLinkType.EMAIL:
                href = f"mailto:{item.custom_target}"
            elif link_type == NavigationLinkType.PHONE:
                phone = re.sub(r"[^+0-9]", "", item.custom_target or "")
                href = f"tel:{phone}"
            resolved.append(
                {
                    "item": item,
                    "target_label": target_label,
                    "href": href,
                    "content_text": item.content_text,
                    "status": target_status,
                    "eligible": eligible,
                    "reason": reason,
                }
            )
        return resolved


def _validate_menu_items(
    menu: NavigationMenu,
    items: list[NavigationItemData],
) -> list[NavigationItemData]:
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise ConflictError(
            "Each menu item must have a unique ID.",
            code="NAVIGATION_DUPLICATE_ITEM",
        )
    by_id = {item.id: item for item in items}
    children: dict[UUID, list[NavigationItemData]] = defaultdict(list)
    for item in items:
        if item.parent_id is None:
            continue
        parent = by_id.get(item.parent_id)
        if parent is None:
            raise ConflictError(
                "Each submenu item must belong to a top-level item in this menu.",
                code="NAVIGATION_INVALID_PARENT",
            )
        if parent.parent_id is not None:
            raise ConflictError(
                "Navigation supports only one level of dropdowns.",
                code="NAVIGATION_NESTING_LIMIT",
            )
        if parent.link_type != NavigationLinkType.NONE:
            raise ConflictError(
                "A dropdown parent must be a non-clickable heading.",
                code="NAVIGATION_HEADING_MUST_NOT_LINK",
            )
        children[parent.id].append(item)

    for item in items:
        if item.link_type == NavigationLinkType.NONE and not children.get(item.id):
            raise ConflictError(
                "A dropdown heading needs at least one submenu item.",
                code="NAVIGATION_EMPTY_HEADING",
            )

    counts: dict[UUID | None, int] = defaultdict(int)
    normalized: list[NavigationItemData] = []
    for item in items:
        targets = {
            "PAGE": item.page_id,
            "PROJECT": item.project_id,
            "POST": item.post_id,
            "CATEGORY": item.category_id,
            "ROUTE": item.route_key,
            "EXTERNAL": item.custom_target,
            "EMAIL": item.custom_target,
            "PHONE": item.custom_target,
            "TEXT": item.content_text,
        }
        expected = targets.get(item.link_type.value)
        populated = [
            value
            for value in (
                item.page_id,
                item.project_id,
                item.post_id,
                item.category_id,
                item.route_key,
                item.custom_target,
                item.content_text,
            )
            if value is not None
        ]
        if item.link_type == NavigationLinkType.NONE:
            if populated:
                raise ConflictError(
                    "Dropdown headings cannot have a destination.",
                    code="NAVIGATION_INVALID_TARGET",
                )
        elif expected is None or len(populated) != 1:
            raise ConflictError(
                "Choose exactly one destination matching the link type.",
                code="NAVIGATION_INVALID_TARGET",
            )

        footer_types = {
            NavigationLinkType.EXTERNAL,
            NavigationLinkType.EMAIL,
            NavigationLinkType.PHONE,
            NavigationLinkType.TEXT,
        }
        if item.link_type in footer_types and menu != NavigationMenu.FOOTER:
            raise ConflictError(
                "Custom links and text are only available in the footer.",
                code="NAVIGATION_FOOTER_CONTENT_ONLY",
            )
        custom_target = item.custom_target.strip() if item.custom_target else None
        content_text = item.content_text.strip() if item.content_text else None
        if item.link_type == NavigationLinkType.EXTERNAL:
            parsed = urlsplit(custom_target or "")
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ConflictError(
                    "External footer links must use a valid https:// URL.",
                    code="NAVIGATION_INVALID_EXTERNAL_URL",
                )
        elif item.link_type == NavigationLinkType.EMAIL and not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", custom_target or ""
        ):
            raise ConflictError(
                "Enter a valid email address.",
                code="NAVIGATION_INVALID_EMAIL",
            )
        elif item.link_type == NavigationLinkType.PHONE:
            digits = re.sub(r"\D", "", custom_target or "")
            if (
                not re.fullmatch(r"\+?[0-9][0-9 ().-]{5,24}", custom_target or "")
                or not 7 <= len(digits) <= 15
            ):
                raise ConflictError(
                    "Enter a valid phone number.",
                    code="NAVIGATION_INVALID_PHONE",
                )
        if item.link_type == NavigationLinkType.TEXT and (
            not content_text or len(content_text) > 1000
        ):
            raise ConflictError(
                "Footer text must contain between 1 and 1000 characters.",
                code="NAVIGATION_INVALID_TEXT",
            )

        normalized.append(
            NavigationItemData(
                id=item.id,
                parent_id=item.parent_id,
                label=item.label.strip(),
                link_type=item.link_type,
                page_id=item.page_id,
                project_id=item.project_id,
                post_id=item.post_id,
                category_id=item.category_id,
                route_key=item.route_key,
                custom_target=custom_target,
                content_text=content_text,
                is_visible=item.is_visible,
                display_order=counts[item.parent_id],
            )
        )
        counts[item.parent_id] += 1
    return normalized


def _public_tree(
    resolved: list[dict[str, object]],
) -> list[NavigationPublicItem]:
    children: dict[UUID, list[dict[str, object]]] = defaultdict(list)
    for entry in resolved:
        item: NavigationItem = entry["item"]
        if item.parent_id is not None:
            children[item.parent_id].append(entry)

    roots: list[NavigationPublicItem] = []
    for entry in resolved:
        item: NavigationItem = entry["item"]
        if item.parent_id is not None or not item.is_visible:
            continue
        if item.link_type == NavigationLinkType.NONE:
            visible_children = [
                NavigationPublicItem(
                    id=child["item"].id,
                    label=child["item"].label,
                    link_type=NavigationLinkType(child["item"].link_type),
                    href=child["href"],
                    content_text=child["content_text"],
                    children=[],
                )
                for child in children.get(item.id, [])
                if child["item"].is_visible
                and child["eligible"]
                and (
                    child["href"] is not None
                    or (
                        child["item"].link_type == NavigationLinkType.TEXT
                        and child["content_text"] is not None
                    )
                )
            ]
            if visible_children:
                roots.append(
                    NavigationPublicItem(
                        id=item.id,
                        label=item.label,
                        link_type=NavigationLinkType(item.link_type),
                        href=None,
                        content_text=None,
                        children=visible_children,
                    )
                )
        elif entry["eligible"] and (
            entry["href"] is not None
            or (
                item.link_type == NavigationLinkType.TEXT
                and entry["content_text"] is not None
            )
        ):
            roots.append(
                NavigationPublicItem(
                    id=item.id,
                    label=item.label,
                    link_type=NavigationLinkType(item.link_type),
                    href=entry["href"],
                    content_text=entry["content_text"],
                    children=[],
                )
            )
    return roots


def _audit_items(items: list[NavigationItem]) -> list[dict[str, object]]:
    ordered = sorted(
        items,
        key=lambda item: (
            item.parent_id is not None,
            str(item.parent_id or ""),
            item.display_order,
        ),
    )
    return [
        {
            "id": str(item.id),
            "parent_id": str(item.parent_id) if item.parent_id else None,
            "label": item.label,
            "link_type": str(getattr(item.link_type, "value", item.link_type)),
            "page_id": str(item.page_id) if item.page_id else None,
            "project_id": str(item.project_id) if item.project_id else None,
            "post_id": str(item.post_id) if item.post_id else None,
            "category_id": str(item.category_id) if item.category_id else None,
            "route_key": item.route_key,
            "custom_target": item.custom_target,
            "content_text": item.content_text,
            "display_order": item.display_order,
            "is_visible": item.is_visible,
        }
        for item in ordered
    ]


def _audit_data(
    items: list[NavigationItemData],
    _menu: NavigationMenu,
) -> list[dict[str, object]]:
    ordered = sorted(
        items,
        key=lambda item: (
            item.parent_id is not None,
            str(item.parent_id or ""),
            item.display_order,
        ),
    )
    return [
        {
            "id": str(item.id),
            "parent_id": str(item.parent_id) if item.parent_id else None,
            "label": item.label,
            "link_type": item.link_type.value,
            "page_id": str(item.page_id) if item.page_id else None,
            "project_id": str(item.project_id) if item.project_id else None,
            "post_id": str(item.post_id) if item.post_id else None,
            "category_id": str(item.category_id) if item.category_id else None,
            "route_key": item.route_key,
            "custom_target": item.custom_target,
            "content_text": item.content_text,
            "display_order": item.display_order,
            "is_visible": item.is_visible,
        }
        for item in ordered
    ]
