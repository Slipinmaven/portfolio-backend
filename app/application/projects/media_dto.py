from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.database.models.enums import ProjectMediaRole


@dataclass(frozen=True)
class ProjectMediaCreateDTO:
    media_id: UUID
    role: ProjectMediaRole
    display_order: int = 0
    caption: str | None = None


@dataclass(frozen=True)
class ProjectMediaUpdateDTO:
    display_order: int | None = None
    caption: str | None = None
    fields_set: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ProjectMediaOrderDTO:
    role: ProjectMediaRole
    media_ids: tuple[UUID, ...]
