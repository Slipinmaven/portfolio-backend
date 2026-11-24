from dataclasses import dataclass
from app.infrastructure.database.models.enums import ResourceStatus, ResourceType


@dataclass(frozen=True)
class ResourceListFilters:
    offset: int = 0
    limit: int = 50
    status: ResourceStatus | None = None
    resource_type: ResourceType | None = None
    published_only: bool = False


@dataclass(frozen=True)
class ResourceCreateData:
    title: str
    url: str
    resource_type: ResourceType
    creator: str | None = None
    summary: str | None = None
    commentary: str | None = None


@dataclass(frozen=True)
class ResourceUpdateData:
    title: str | None = None
    url: str | None = None
    resource_type: ResourceType | None = None
    creator: str | None = None
    summary: str | None = None
    commentary: str | None = None
    status: ResourceStatus | None = None
    fields_set: frozenset[str] = frozenset()


