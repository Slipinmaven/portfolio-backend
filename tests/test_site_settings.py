import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.application.site_settings.dto import (
    SiteLinkData,
    SiteSettingsUpdateData,
)
from app.application.errors import ConflictError
from app.application.site_settings.service import SiteSettingsService
from app.infrastructure.database.models.enums import SiteLinkPlatform, UserRole
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.models.user import User
from app.infrastructure.database.unit_of_work.site_settings import (
    SiteSettingsUnitOfWork,
)
from app.main import app
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.services import get_site_settings_service
from app.presentation.schemas.site_settings import SiteLinkInput


class SiteSettingsServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = SiteSettings(
            id=1,
            site_name="Portfolio",
            owner_name="Owner",
            language_code="en",
            title_template="{title} | {site_name}",
        )
        self.uow = MagicMock(spec=SiteSettingsUnitOfWork)
        self.uow.settings = MagicMock()
        self.uow.settings.get_singleton = AsyncMock(return_value=self.settings)
        self.uow.links = MagicMock()
        self.uow.links.list_ordered = AsyncMock(return_value=[])
        self.uow.links.delete_except = AsyncMock()
        self.uow.media = MagicMock()
        self.uow.media.get_by_ids = AsyncMock(return_value=[])
        self.uow.audit_logs = MagicMock()
        self.uow.audit_logs.create = AsyncMock()
        self.uow.session = MagicMock()
        self.uow.session.add = MagicMock()
        self.uow.session.flush = AsyncMock()
        self.uow.session.refresh = AsyncMock()
        self.uow.commit = AsyncMock()
        self.uow.rollback = AsyncMock()
        self.service = SiteSettingsService(self.uow)

    def update_data(self, links: list[SiteLinkData]) -> SiteSettingsUpdateData:
        return SiteSettingsUpdateData(
            site_name="Portfolio",
            tagline=None,
            owner_name="Owner",
            role_title=None,
            owner_bio=None,
            location=None,
            availability_note=None,
            language_code="en",
            title_template="{title} | {site_name}",
            default_description=None,
            logo_media_id=None,
            favicon_media_id=None,
            default_social_image_media_id=None,
            profile_image_media_id=None,
            links=links,
        )

    async def test_new_links_are_kept_during_full_settings_sync(self) -> None:
        async def verify_updated_at_refresh(
            settings: SiteSettings,
            *,
            attribute_names: list[str],
        ) -> None:
            self.assertIs(settings, self.settings)
            self.assertEqual(attribute_names, ["updated_at"])
            self.uow.commit.assert_not_awaited()

        self.uow.session.refresh.side_effect = verify_updated_at_refresh
        result = await self.service.update_settings(
            self.update_data(
                [
                    SiteLinkData(
                        id=None,
                        platform=SiteLinkPlatform.GITHUB,
                        url="https://github.com/owner",
                        label=None,
                    )
                ]
            ),
            actor_id=uuid4(),
        )

        self.assertEqual(len(result.links), 1)
        self.assertIsInstance(result.links[0].id, UUID)
        self.uow.links.delete_except.assert_awaited_once_with(
            {result.links[0].id}
        )
        self.uow.session.add.assert_called_once_with(result.links[0])
        self.uow.session.refresh.assert_awaited_once_with(
            self.settings,
            attribute_names=["updated_at"],
        )
        self.uow.commit.assert_awaited_once()

    async def test_duplicate_destinations_are_rejected_before_writing(self) -> None:
        with self.assertRaises(ConflictError) as context:
            await self.service.update_settings(
                self.update_data(
                    [
                        SiteLinkData(
                            id=None,
                            platform=SiteLinkPlatform.GITHUB,
                            url="https://example.com/profile",
                            label=None,
                        ),
                        SiteLinkData(
                            id=None,
                            platform=SiteLinkPlatform.OTHER,
                            url="https://example.com/profile",
                            label=None,
                        ),
                    ]
                ),
                actor_id=uuid4(),
            )

        self.assertEqual(
            context.exception.code,
            "SITE_LINK_DUPLICATE_DESTINATION",
        )
        self.assertIn("Contact links 1 and 2", context.exception.message)
        self.uow.session.flush.assert_not_awaited()
        self.uow.commit.assert_not_awaited()

    async def test_whatsapp_constraint_explains_pending_database_migration(
        self,
    ) -> None:
        self.uow.session.flush.side_effect = IntegrityError(
            "statement",
            {},
            SimpleNamespace(
                orig=SimpleNamespace(
                    constraint_name="ck_site_links_platform",
                )
            ),
        )

        with self.assertRaises(ConflictError) as context:
            await self.service.update_settings(
                self.update_data(
                    [
                        SiteLinkData(
                            id=None,
                            platform=SiteLinkPlatform.WHATSAPP,
                            url="https://wa.me/254712345678",
                            label=None,
                        )
                    ]
                ),
                actor_id=uuid4(),
            )

        self.assertEqual(
            context.exception.code,
            "SITE_LINK_PLATFORM_MIGRATION_REQUIRED",
        )
        self.assertIn("database has not been upgraded", context.exception.message)
        self.assertIn("None of your changes were saved", context.exception.message)
        self.uow.rollback.assert_awaited_once()
        self.uow.commit.assert_not_awaited()

    def test_social_links_require_https_and_email_uses_mailto(self) -> None:
        with self.assertRaises(ValidationError):
            SiteLinkInput(platform="GITHUB", url="http://github.com/owner")

        with self.assertRaises(ValidationError):
            SiteLinkInput(platform="EMAIL", url="owner@example.com")

        email = SiteLinkInput(
            platform="EMAIL",
            url="mailto:owner@example.com",
        )
        self.assertEqual(email.url, "mailto:owner@example.com")

    def test_whatsapp_links_require_an_international_wa_me_number(self) -> None:
        with self.assertRaises(ValidationError):
            SiteLinkInput(
                platform="WHATSAPP",
                url="https://wa.me/0712345678",
            )

        with self.assertRaises(ValidationError):
            SiteLinkInput(
                platform="WHATSAPP",
                url="https://example.com/254712345678",
            )

        whatsapp = SiteLinkInput(
            platform="WHATSAPP",
            url="https://wa.me/254712345678?text=Hello",
        )
        self.assertEqual(whatsapp.url, "https://wa.me/254712345678?text=Hello")


class SiteSettingsRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_editor_cannot_read_admin_site_settings(self) -> None:
        editor = User(
            id=uuid4(),
            email="editor@example.com",
            password_hash="hashed",
            first_name="Editor",
            last_name="User",
            role=UserRole.EDITOR,
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: editor
        app.dependency_overrides[get_site_settings_service] = lambda: object()

        with TestClient(app) as client:
            response = client.get("/api/v1/site-settings/admin")

        self.assertEqual(response.status_code, 403)
