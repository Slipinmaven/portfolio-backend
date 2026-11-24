from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.tags.dto import CreateTagData, TagListFilters, UpdateTagData
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.tag import Tag
from app.infrastructure.database.unit_of_work.catalog import CatalogUnitOfWork


class TagService:
    def __init__(self, unit_of_work: CatalogUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_tags(self, filters: TagListFilters) -> tuple[list[Tag], int]:
        return await self._unit_of_work.tags.list_tags(
            offset=filters.offset,
            limit=filters.limit,
            is_active=filters.is_active,
        )

    async def get_tag(self, tag_id: UUID) -> Tag:
        tag = await self._unit_of_work.tags.get_by_id(tag_id)
        if tag is None:
            raise ResourceNotFoundError("Tag not found.")
        return tag

    async def get_active_tag(self, tag_id: UUID) -> Tag:
        tag = await self._unit_of_work.tags.get_by_id(tag_id)
        if tag is None or not tag.is_active:
            raise ResourceNotFoundError("Tag not found.")
        return tag

    async def create_tag(self, data: CreateTagData, *, actor_id: UUID) -> Tag:
        tag = Tag(
            name=data.name.strip(),
            slug=data.slug.strip(),
            description=data.description.strip() if data.description else data.description,
            is_active=data.is_active,
        )
        try:
            await self._unit_of_work.tags.create(tag)
            await self._record_audit(
                actor_id=actor_id,
                tag_id=tag.id,
                action="tag.created",
                new_values={"name": tag.name, "slug": tag.slug},
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError("A tag with this slug or name already exists.") from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return tag

    async def update_tag(
        self,
        tag_id: UUID,
        data: UpdateTagData,
        *,
        actor_id: UUID,
    ) -> Tag:
        tag = await self.get_tag(tag_id)
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}
        for field in ("name", "slug", "description", "is_active"):
            if field not in data.fields_set:
                continue
            value = getattr(data, field)
            if isinstance(value, str):
                value = value.strip()
            old_value = getattr(tag, field)
            if old_value == value:
                continue
            old_values[field] = old_value
            new_values[field] = value
            setattr(tag, field, value)

        try:
            if new_values:
                await self._record_audit(
                    actor_id=actor_id,
                    tag_id=tag.id,
                    action="tag.updated",
                    old_values=old_values,
                    new_values=new_values,
                )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError("The tag update conflicts with an existing tag.") from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return tag

    async def delete_tag(self, tag_id: UUID, *, actor_id: UUID) -> None:
        tag = await self.get_tag(tag_id)
        try:
            await self._unit_of_work.tags.delete(tag)
            await self._record_audit(
                actor_id=actor_id,
                tag_id=tag.id,
                action="tag.deleted",
                old_values={"name": tag.name, "slug": tag.slug},
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            raise ConflictError("The tag cannot be deleted while it is assigned to projects.") from exc
        except BaseException:
            await self._unit_of_work.rollback()
            raise

    async def _record_audit(
        self,
        *,
        actor_id: UUID,
        tag_id: UUID,
        action: str,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
    ) -> None:
        await self._unit_of_work.audit_logs.create(
            AuditLog(
                user_id=actor_id,
                action=action,
                entity_type="tag",
                entity_id=tag_id,
                old_values=old_values,
                new_values=new_values,
                status="success",
            )
        )
