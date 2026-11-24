import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.application.errors import ConflictError
from app.application.navigation.dto import NavigationItemData
from app.application.navigation.service import (
    NavigationService,
    _public_tree,
    _validate_menu_items,
)
from app.infrastructure.database.models.enums import NavigationLinkType, NavigationMenu
from app.infrastructure.database.models.navigation_item import NavigationItem
from app.presentation.schemas.navigation import NavigationItemInput


def _item_data(
    link_type: NavigationLinkType,
    *,
    custom_target: str | None = None,
    content_text: str | None = None,
) -> NavigationItemData:
    return NavigationItemData(
        id=uuid4(),
        parent_id=None,
        label="Footer item",
        link_type=link_type,
        page_id=None,
        project_id=None,
        post_id=None,
        category_id=None,
        route_key=None,
        custom_target=custom_target,
        content_text=content_text,
        is_visible=True,
    )


def _navigation_item(
    link_type: NavigationLinkType,
    *,
    label: str,
    parent_id: UUID | None = None,
    custom_target: str | None = None,
    content_text: str | None = None,
) -> NavigationItem:
    return NavigationItem(
        id=uuid4(),
        menu=NavigationMenu.FOOTER,
        parent_id=parent_id,
        label=label,
        link_type=link_type,
        custom_target=custom_target,
        content_text=content_text,
        is_visible=True,
    )


class NavigationFooterContentTests(unittest.IsolatedAsyncioTestCase):
    def test_footer_input_accepts_custom_links_and_text(self) -> None:
        inputs = [
            NavigationItemInput(
                id=uuid4(),
                label="Portfolio",
                link_type=NavigationLinkType.EXTERNAL,
                custom_target="https://example.com",
            ),
            NavigationItemInput(
                id=uuid4(),
                label="Email",
                link_type=NavigationLinkType.EMAIL,
                custom_target="hello@example.com",
            ),
            NavigationItemInput(
                id=uuid4(),
                label="Call",
                link_type=NavigationLinkType.PHONE,
                custom_target="+1 (555) 123-4567",
            ),
            NavigationItemInput(
                id=uuid4(),
                label="Availability",
                link_type=NavigationLinkType.TEXT,
                content_text="Open to select projects.",
            ),
        ]
        self.assertEqual(len(inputs), 4)

    def test_custom_content_is_limited_to_footer_menu(self) -> None:
        with self.assertRaises(ConflictError):
            _validate_menu_items(
                NavigationMenu.HEADER,
                [
                    _item_data(
                        NavigationLinkType.EXTERNAL,
                        custom_target="https://example.com",
                    )
                ],
            )

        footer_items = _validate_menu_items(
            NavigationMenu.FOOTER,
            [
                _item_data(
                    NavigationLinkType.EXTERNAL,
                    custom_target="https://example.com",
                ),
                _item_data(
                    NavigationLinkType.EMAIL,
                    custom_target="hello@example.com",
                ),
                _item_data(
                    NavigationLinkType.PHONE,
                    custom_target="+1 (555) 123-4567",
                ),
                _item_data(
                    NavigationLinkType.TEXT,
                    content_text="Available for select projects.",
                ),
            ],
        )
        self.assertEqual(len(footer_items), 4)

    def test_external_footer_urls_must_use_https(self) -> None:
        with self.assertRaises(ValidationError):
            NavigationItemInput(
                id=uuid4(),
                label="Unsafe",
                link_type=NavigationLinkType.EXTERNAL,
                custom_target="javascript:alert(1)",
            )

    async def test_public_footer_resolves_custom_links_and_text(self) -> None:
        empty_repository = SimpleNamespace(get_by_ids=AsyncMock(return_value=[]))
        service = NavigationService(
            SimpleNamespace(
                pages=empty_repository,
                projects=empty_repository,
                posts=empty_repository,
                categories=empty_repository,
            )
        )
        section = _navigation_item(
            NavigationLinkType.NONE,
            label="Contact",
        )
        text = _navigation_item(
            NavigationLinkType.TEXT,
            label="Availability",
            parent_id=section.id,
            content_text="Open to select projects.",
        )
        external = _navigation_item(
            NavigationLinkType.EXTERNAL,
            label="Portfolio",
            custom_target="https://example.com",
        )
        email = _navigation_item(
            NavigationLinkType.EMAIL,
            label="Email",
            custom_target="hello@example.com",
        )
        phone = _navigation_item(
            NavigationLinkType.PHONE,
            label="Call",
            custom_target="+1 (555) 123-4567",
        )

        resolved = await service._resolve_items(
            [section, text, external, email, phone]
        )
        public_items = _public_tree(resolved)

        self.assertEqual(public_items[0].label, "Contact")
        self.assertEqual(
            public_items[0].children[0].content_text,
            "Open to select projects.",
        )
        self.assertEqual(public_items[1].href, "https://example.com")
        self.assertEqual(public_items[2].href, "mailto:hello@example.com")
        self.assertEqual(public_items[3].href, "tel:+15551234567")
