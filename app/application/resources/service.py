from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, ResourceNotFoundError
from app.application.resources.dto import (
    ResourceCreateData,
    ResourceListFilters,
    ResourceUpdateData,
)
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import ResourceStatus
from app.infrastructure.database.models.resource import Resource
from app.infrastructure.database.unit_of_work.resources import ResourcesUnitOfWork


class ResourceService:
    def __init__(self, unit_of_work: ResourcesUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def list_resources(
        self,
        filters: ResourceListFilters,
    ) -> tuple[list[Resource], int]:
        return await self._unit_of_work.resources.list_resources(
            offset=filters.offset,
            limit=filters.limit,
            status=filters.status,
            resource_type=filters.resource_type,
            published_only=filters.published_only,
        )

    async def get_resource(self, resource_id: UUID) -> Resource:
        resource = await self._unit_of_work.resources.get_by_id(resource_id)
        if resource is None:
            raise ResourceNotFoundError("Resource not found.")
        return resource

    async def get_published_resource(self, resource_id: UUID) -> Resource:
        resource = await self.get_resource(resource_id)
        if ResourceStatus(resource.status) != ResourceStatus.PUBLISHED:
            raise ResourceNotFoundError("Resource not found.")
        return resource

    async def create_resource(
        self,
        data: ResourceCreateData,
        *,
        actor_id: UUID,
    ) -> Resource:
        url = normalize_resource_url(data.url)
        if await self._unit_of_work.resources.get_by_url(url):
            raise ConflictError(
                "A resource with this destination URL already exists.",
                code="RESOURCE_URL_CONFLICT",
            )

        resource = Resource(
            title=data.title.strip(),
            url=url,
            resource_type=data.resource_type,
            creator=_optional_text(data.creator),
            summary=_optional_text(data.summary),
            commentary=_optional_text(data.commentary),
            status=ResourceStatus.DRAFT,
            published_at=None,
            archived_at=None,
        )
        try:
            await self._unit_of_work.resources.create(resource)
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="resource.created",
                    entity_type="resource",
                    entity_id=resource.id,
                    new_values=_audit_values(resource),
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            if await self._unit_of_work.resources.get_by_url(url):
                raise ConflictError(
                    "A resource with this destination URL already exists.",
                    code="RESOURCE_URL_CONFLICT",
                ) from exc
            raise
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return resource

    async def update_resource(
        self,
        resource_id: UUID,
        data: ResourceUpdateData,
        *,
        actor_id: UUID,
    ) -> Resource:
        resource = await self.get_resource(resource_id)
        old_values: dict[str, object] = {}
        new_values: dict[str, object] = {}

        for field in (
            "title",
            "url",
            "resource_type",
            "creator",
            "summary",
            "commentary",
        ):
            if field not in data.fields_set:
                continue
            value = getattr(data, field)
            if field == "title":
                value = value.strip()
            elif field == "url":
                value = normalize_resource_url(value or "")
                existing = await self._unit_of_work.resources.get_by_url(value)
                if existing is not None and existing.id != resource.id:
                    raise ConflictError(
                        "A resource with this destination URL already exists.",
                        code="RESOURCE_URL_CONFLICT",
                    )
            elif field in {"creator", "summary"}:
                value = _optional_text(value)
            if field == "commentary":
                value = value.strip() if value and value.strip() else None
            old_value = getattr(resource, field)
            if old_value == value:
                continue
            old_values[field] = _audit_value(old_value)
            new_values[field] = _audit_value(value)
            setattr(resource, field, value)

        final_status = (
            data.status
            if "status" in data.fields_set and data.status is not None
            else ResourceStatus(resource.status)
        )
        if final_status == ResourceStatus.PUBLISHED:
            if resource.published_at is None:
                resource.published_at = datetime.now(timezone.utc)
                new_values["published_at"] = _audit_value(resource.published_at)
            if resource.archived_at is not None:
                old_values["archived_at"] = _audit_value(resource.archived_at)
                resource.archived_at = None
                new_values["archived_at"] = None
        elif final_status == ResourceStatus.ARCHIVED:
            if resource.archived_at is None:
                resource.archived_at = datetime.now(timezone.utc)
                new_values["archived_at"] = _audit_value(resource.archived_at)
        elif resource.archived_at is not None:
            old_values["archived_at"] = _audit_value(resource.archived_at)
            resource.archived_at = None
            new_values["archived_at"] = None

        current_status = ResourceStatus(resource.status)
        if current_status != final_status:
            old_values["status"] = current_status.value
            new_values["status"] = final_status.value
            resource.status = final_status

        try:
            if new_values:
                await self._unit_of_work.audit_logs.create(
                    AuditLog(
                        user_id=actor_id,
                        action="resource.updated",
                        entity_type="resource",
                        entity_id=resource.id,
                        old_values=old_values,
                        new_values=new_values,
                        status="success",
                    )
                )
            await self._unit_of_work.commit()
        except IntegrityError as exc:
            await self._unit_of_work.rollback()
            if await self._unit_of_work.resources.get_by_url(resource.url):
                raise ConflictError(
                    "A resource with this destination URL already exists.",
                    code="RESOURCE_URL_CONFLICT",
                ) from exc
            raise
        except BaseException:
            await self._unit_of_work.rollback()
            raise
        return resource

    async def delete_resource(
        self,
        resource_id: UUID,
        *,
        actor_id: UUID,
    ) -> None:
        resource = await self.get_resource(resource_id)
        old_values = _audit_values(resource)
        try:
            await self._unit_of_work.resources.delete(resource)
            await self._unit_of_work.audit_logs.create(
                AuditLog(
                    user_id=actor_id,
                    action="resource.deleted",
                    entity_type="resource",
                    entity_id=resource.id,
                    old_values=old_values,
                    status="success",
                )
            )
            await self._unit_of_work.commit()
        except BaseException:
            await self._unit_of_work.rollback()
            raise


def normalize_resource_url(value: str) -> str:
    candidate = value.strip()
    if not candidate or any(ord(char) < 32 or char.isspace() for char in candidate):
        raise _invalid_url()
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError as exc:
        raise _invalid_url() from exc
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise _invalid_url()
    hostname = parts.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname if port is None else f"{hostname}:{port}"
    normalized = urlunsplit(
        ("https", netloc, parts.path, parts.query, parts.fragment)
    )
    if len(normalized) > 500:
        raise ConflictError(
            "Resource URLs can be at most 500 characters.",
            code="RESOURCE_URL_INVALID",
        )
    return normalized


def _invalid_url() -> ConflictError:
    return ConflictError(
        "Enter a valid HTTPS destination URL without embedded credentials.",
        code="RESOURCE_URL_INVALID",
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _audit_values(resource: Resource) -> dict[str, object]:
    return {
        "title": resource.title,
        "url": resource.url,
        "resource_type": _audit_value(resource.resource_type),
        "creator": resource.creator,
        "summary": resource.summary,
        "status": _audit_value(resource.status),
        "published_at": _audit_value(resource.published_at),
        "archived_at": _audit_value(resource.archived_at),
    }


def _audit_value(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
