import re
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy.exc import IntegrityError

from app.application.errors import (
    ConflictError,
    MediaValidationError,
    ResourceNotFoundError,
)
from app.application.site_settings.dto import (
    SiteLinkData,
    SiteSettingsBundle,
    SiteSettingsUpdateData,
)
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import MediaKind
from app.infrastructure.database.models.site_link import SiteLink
from app.infrastructure.database.models.site_settings import SiteSettings
from app.infrastructure.database.unit_of_work.site_settings import (
    SiteSettingsUnitOfWork,
)

_SITE_SETTINGS_AUDIT_ID = uuid5(NAMESPACE_URL, "portfolio:site-settings:1")
_ALLOWED_TITLE_PLACEHOLDERS = {"title", "site_name"}
_FAVICON_MIME_TYPES = {
    "image/png",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}


def _integrity_constraint_name(error: IntegrityError) -> str | None:
    original = error.orig
    candidates = (original, getattr(original, "orig", None))
    for candidate in candidates:
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
        diagnostic = getattr(candidate, "diag", None)
        constraint_name = getattr(diagnostic, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
    return None


class SiteSettingsService:
    def __init__(self, unit_of_work: SiteSettingsUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def get_settings(self) -> SiteSettingsBundle:
        settings = await self._unit_of_work.settings.get_singleton()
        if settings is None:
            raise ResourceNotFoundError("Site settings have not been initialized.")
        return SiteSettingsBundle(
            settings=settings,
            links=await self._unit_of_work.links.list_ordered(),
        )

    async def update_settings(
        self,
        data: SiteSettingsUpdateData,
        *,
        actor_id: UUID,
    ) -> SiteSettingsBundle:
        settings = await self._unit_of_work.settings.get_singleton(for_update=True)
        if settings is None:
            raise ResourceNotFoundError("Site settings have not been initialized.")

        self._validate_title_template(data.title_template)
        await self._validate_media(data)

        current_links = await self._unit_of_work.links.list_ordered()
        current_by_id = {link.id: link for link in current_links}
        requested_ids = [link.id for link in data.links if link.id is not None]
        if len(set(requested_ids)) != len(requested_ids):
            raise ConflictError("A social link was included more than once.")
        if any(link_id not in current_by_id for link_id in requested_ids):
            raise ResourceNotFoundError("A social link no longer exists.")

        destination_indexes: dict[str, int] = {}
        for index, link in enumerate(data.links):
            destination = link.url.strip()
            if destination in destination_indexes:
                first_index = destination_indexes[destination]
                raise ConflictError(
                    f"Contact links {first_index + 1} and {index + 1} use the "
                    "same destination. Change or remove one of them.",
                    code="SITE_LINK_DUPLICATE_DESTINATION",
                )
            destination_indexes[destination] = index

        old_values = {
            "settings": self._settings_values(settings),
            "links": [self._link_values(link) for link in current_links],
        }
        new_values = {
            "settings": self._settings_values(data),
            "links": [
                self._input_link_values(link, index)
                for index, link in enumerate(data.links)
            ],
        }

        settings_changed = old_values["settings"] != new_values["settings"]
        links_changed = old_values["links"] != new_values["links"]
        if not settings_changed and not links_changed:
            return SiteSettingsBundle(settings=settings, links=current_links)

        for field in (
            "site_name",
            "tagline",
            "owner_name",
            "role_title",
            "owner_bio",
            "location",
            "availability_note",
            "language_code",
            "title_template",
            "default_description",
            "logo_media_id",
            "favicon_media_id",
            "default_social_image_media_id",
            "profile_image_media_id",
        ):
            value = getattr(data, field)
            if field in {
                "tagline",
                "role_title",
                "owner_bio",
                "location",
                "availability_note",
                "default_description",
            }:
                value = _optional_text(value)
            setattr(settings, field, value)

        kept_ids: set[UUID] = set()
        updated_links: list[SiteLink] = []
        for index, link_data in enumerate(data.links):
            link = (
                current_by_id[link_data.id]
                if link_data.id is not None
                else SiteLink(id=uuid4())
            )
            link.platform = link_data.platform.value
            link.url = link_data.url.strip()
            link.label = _optional_text(link_data.label)
            link.display_order = index
            if link_data.id is not None:
                kept_ids.add(link.id)
            else:
                self._unit_of_work.session.add(link)
                kept_ids.add(link.id)
            updated_links.append(link)

        try:
            await self._unit_of_work.links.delete_except(kept_ids)
            await self._unit_of_work.session.flush()
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="site_settings.updated",
                    entity_type="site_settings",
                    entity_id=_SITE_SETTINGS_AUDIT_ID,
                    old_values=old_values,
                    new_values=new_values,
                    status="success",
                )
            )
            await self._unit_of_work.session.refresh(
                settings,
                attribute_names=["updated_at"],
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            constraint_name = _integrity_constraint_name(exc)
            if constraint_name == "ck_site_links_platform":
                raise ConflictError(
                    "WhatsApp links are available in the editor, but this "
                    "database has not been upgraded to support them. Apply the "
                    "pending WhatsApp site-link migration, then retry. None of "
                    "your changes were saved.",
                    code="SITE_LINK_PLATFORM_MIGRATION_REQUIRED",
                ) from exc
            if constraint_name == "uq_site_links_url":
                raise ConflictError(
                    "Two contact links use the same destination. Change or "
                    "remove the duplicate. None of your changes were saved.",
                    code="SITE_LINK_DUPLICATE_DESTINATION",
                ) from exc
            if constraint_name == "ck_site_links_url":
                raise ConflictError(
                    "A contact link has an invalid destination. Check its URL "
                    "format and try again. None of your changes were saved.",
                    code="SITE_LINK_INVALID_DESTINATION",
                ) from exc
            raise ConflictError(
                "A database constraint prevented these settings from being "
                "saved. Check that each contact destination is unique and "
                "selected images are still available. If this continues, "
                "contact an administrator. None of your changes were saved.",
                code="SITE_SETTINGS_CONSTRAINT_CONFLICT",
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise

        return SiteSettingsBundle(settings=settings, links=updated_links)

    async def _validate_media(self, data: SiteSettingsUpdateData) -> None:
        media_ids = {
            media_id
            for media_id in (
                data.logo_media_id,
                data.favicon_media_id,
                data.default_social_image_media_id,
                data.profile_image_media_id,
            )
            if media_id is not None
        }
        media = await self._unit_of_work.media.get_by_ids(
            sorted(media_ids, key=lambda value: value.int)
        )
        by_id = {item.id: item for item in media}
        for media_id in media_ids:
            item = by_id.get(media_id)
            if item is None:
                raise ResourceNotFoundError("A selected image no longer exists.")
            if item.kind != MediaKind.IMAGE:
                raise MediaValidationError("Site settings can only use image media.")
        if data.favicon_media_id is not None:
            favicon = by_id[data.favicon_media_id]
            if favicon.mime_type.lower() not in _FAVICON_MIME_TYPES:
                raise MediaValidationError(
                    "The favicon must be a PNG, SVG, or ICO image."
                )

    @staticmethod
    def _validate_title_template(value: str) -> None:
        placeholders = re.findall(r"\{([^{}]+)\}", value)
        if "{title}" not in value or any(
            placeholder not in _ALLOWED_TITLE_PLACEHOLDERS
            for placeholder in placeholders
        ):
            raise ConflictError(
                "The title template must include {title} and may only use "
                "{title} and {site_name}."
            )
        if re.search(r"\{[^{}]*\}|\{|\}", re.sub(
            r"\{(?:title|site_name)\}", "", value
        )):
            raise ConflictError("The title template contains an invalid token.")

    @staticmethod
    def _settings_values(
        settings: SiteSettings | SiteSettingsUpdateData,
    ) -> dict[str, object]:
        fields = (
            "site_name",
            "tagline",
            "owner_name",
            "role_title",
            "owner_bio",
            "location",
            "availability_note",
            "language_code",
            "title_template",
            "default_description",
            "logo_media_id",
            "favicon_media_id",
            "default_social_image_media_id",
            "profile_image_media_id",
        )
        return {
            field: (
                str(value)
                if field.endswith("_media_id") and value is not None
                else value
            )
            for field in fields
            if (value := getattr(settings, field)) is not None
            or field
            in {
                "tagline",
                "role_title",
                "owner_bio",
                "location",
                "availability_note",
                "default_description",
                "logo_media_id",
                "favicon_media_id",
                "default_social_image_media_id",
                "profile_image_media_id",
            }
        }

    @staticmethod
    def _link_values(link: SiteLink) -> dict[str, object]:
        return {
            "id": str(link.id),
            "platform": getattr(link.platform, "value", link.platform),
            "url": link.url,
            "label": link.label,
            "display_order": link.display_order,
        }

    @staticmethod
    def _input_link_values(
        link: SiteLinkData,
        display_order: int,
    ) -> dict[str, object]:
        return {
            "id": str(link.id) if link.id else None,
            "platform": link.platform.value,
            "url": link.url.strip(),
            "label": _optional_text(link.label),
            "display_order": display_order,
        }


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
