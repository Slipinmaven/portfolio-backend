from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.errors import (
    ConflictError,
    MediaValidationError,
    ResourceNotFoundError,
)
from app.application.projects.media_dto import (
    ProjectMediaCreateDTO,
    ProjectMediaOrderDTO,
    ProjectMediaUpdateDTO,
)
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import (
    MediaKind,
    ProjectMediaRole,
    ProjectStatus,
)
from app.infrastructure.database.models.project_media import ProjectMedia
from app.infrastructure.database.unit_of_work.project import ProjectUnitOfWork


class ProjectMediaService:
    def __init__(self, unit_of_work: ProjectUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_project_media(self, project_id: UUID) -> list[ProjectMedia]:
        project = await self._unit_of_work.projects.get_with_associations_by_id(
            project_id
        )
        if project is None:
            raise ResourceNotFoundError("Project not found.")
        return await self._unit_of_work.project_media.list_by_project(project_id)

    async def list_published_project_media(self, slug: str) -> list[ProjectMedia]:
        project = await self._unit_of_work.projects.get_published_by_slug(slug)
        if project is None:
            raise ResourceNotFoundError("Project not found.")
        return await self._unit_of_work.project_media.list_by_project(project.id)

    async def add_project_media(
        self,
        project_id: UUID,
        data: ProjectMediaCreateDTO,
        *,
        actor_id: UUID,
    ) -> ProjectMedia:
        project = await self._unit_of_work.projects.get_with_associations_by_id(
            project_id
        )
        if project is None:
            raise ResourceNotFoundError("Project not found.")
        if data.role == ProjectMediaRole.INLINE:
            raise MediaValidationError(
                "Inline media is managed by content tokens, not manual assignment."
            )

        media = await self._unit_of_work.media.get_with_links(data.media_id)
        if media is None:
            raise ResourceNotFoundError("Media not found.")
        if data.role == ProjectMediaRole.COVER and media.kind != MediaKind.IMAGE:
            raise MediaValidationError("A project cover must use an image.")
        if (
            data.role == ProjectMediaRole.GALLERY
            and media.kind == MediaKind.DOCUMENT
        ):
            raise MediaValidationError(
                "Project gallery items must be images or videos."
            )
        if (
            data.role == ProjectMediaRole.ATTACHMENT
            and media.kind != MediaKind.DOCUMENT
        ):
            raise MediaValidationError("Project attachments must be documents.")
        if (
            project.status == ProjectStatus.PUBLISHED
            and media.kind == MediaKind.IMAGE
            and not media.alt_text
        ):
            raise ConflictError(
                "Add alternative text before using this image in a published project."
            )

        association = ProjectMedia(
            project_id=project_id,
            media_id=data.media_id,
            role=data.role,
            display_order=data.display_order,
            caption=_optional_text(data.caption),
        )
        self._unit_of_work.session.add(association)
        try:
            await self._unit_of_work.session.flush()
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="project.media_added",
                    entity_type="project",
                    entity_id=project_id,
                    new_values={
                        "media_id": str(data.media_id),
                        "role": data.role.value,
                    },
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError(
                "This media is already assigned in that role, or the project already has a cover."
            ) from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise

        result = await self._unit_of_work.project_media.get_association(
            project_id,
            data.media_id,
            data.role,
        )
        if result is None:
            raise ResourceNotFoundError("Project media assignment not found.")
        return result

    async def update_project_media(
        self,
        project_id: UUID,
        media_id: UUID,
        role: ProjectMediaRole,
        data: ProjectMediaUpdateDTO,
        *,
        actor_id: UUID,
    ) -> ProjectMedia:
        if not data.fields_set:
            raise MediaValidationError("Provide at least one field to update.")
        association = await self._unit_of_work.project_media.get_association(
            project_id,
            media_id,
            role,
        )
        if association is None:
            raise ResourceNotFoundError("Project media assignment not found.")
        if role == ProjectMediaRole.INLINE:
            raise MediaValidationError(
                "Inline media assignments cannot be edited manually."
            )

        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}
        if "display_order" in data.fields_set and data.display_order is not None:
            if association.display_order != data.display_order:
                old_values["display_order"] = association.display_order
                new_values["display_order"] = data.display_order
                association.display_order = data.display_order
        if "caption" in data.fields_set:
            caption = _optional_text(data.caption)
            if association.caption != caption:
                old_values["caption"] = association.caption
                new_values["caption"] = caption
                association.caption = caption
        if not new_values:
            return association

        try:
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="project.media_updated",
                    entity_type="project",
                    entity_id=project_id,
                    old_values=old_values,
                    new_values={
                        "media_id": str(media_id),
                        "role": role.value,
                        **new_values,
                    },
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return association

    async def reorder_project_media(
        self,
        project_id: UUID,
        data: ProjectMediaOrderDTO,
        *,
        actor_id: UUID,
    ) -> list[ProjectMedia]:
        if data.role == ProjectMediaRole.INLINE:
            raise MediaValidationError("Inline media order is managed by content.")
        if len(data.media_ids) != len(set(data.media_ids)):
            raise MediaValidationError(
                "A media item can appear only once in the order."
            )
        current = await self._unit_of_work.project_media.list_by_project(
            project_id,
            role=data.role,
        )
        if not current:
            if data.media_ids:
                raise ResourceNotFoundError("Project media assignment not found.")
            if await self._unit_of_work.projects.get_with_associations_by_id(
                project_id
            ) is None:
                raise ResourceNotFoundError("Project not found.")
            return []
        if {item.media_id for item in current} != set(data.media_ids):
            raise MediaValidationError(
                "The order must include every assigned media item in this role."
            )

        by_media_id = {item.media_id: item for item in current}
        old_order = [str(item.media_id) for item in current]
        for order, media_id in enumerate(data.media_ids):
            by_media_id[media_id].display_order = order
        if old_order != [str(media_id) for media_id in data.media_ids]:
            try:
                await self._unit_of_work.audit_logs.create(
                    AuditLog(
                        user_id=actor_id,
                        action="project.media_reordered",
                        entity_type="project",
                        entity_id=project_id,
                        old_values={"role": data.role.value, "media_ids": old_order},
                        new_values={
                            "role": data.role.value,
                            "media_ids": [str(media_id) for media_id in data.media_ids],
                        },
                        status="success",
                    )
                )
                await self._unit_of_work.commit()
            except BaseException:
                await self._unit_of_work.rollback()
                raise
        return await self._unit_of_work.project_media.list_by_project(
            project_id,
            role=data.role,
        )

    async def remove_project_media(
        self,
        project_id: UUID,
        media_id: UUID,
        role: ProjectMediaRole,
        *,
        actor_id: UUID,
    ) -> None:
        association = await self._unit_of_work.project_media.get_association(
            project_id,
            media_id,
            role,
        )
        if association is None:
            raise ResourceNotFoundError("Project media assignment not found.")
        if role == ProjectMediaRole.INLINE:
            raise MediaValidationError(
                "Inline media assignments are managed by content tokens."
            )
        try:
            await self._unit_of_work.project_media.delete_association(
                project_id,
                media_id,
                role,
            )
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="project.media_removed",
                    entity_type="project",
                    entity_id=project_id,
                    old_values={
                        "media_id": str(media_id),
                        "role": role.value,
                    },
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except BaseException:
            await self._unit_of_work.rollback()
            raise


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
