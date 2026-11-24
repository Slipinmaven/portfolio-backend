from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTagData:
    name: str
    slug: str
    description: str | None = None
    is_active: bool = False


@dataclass(frozen=True)
class UpdateTagData:
    name: str | None
    slug: str | None
    description: str | None
    is_active: bool | None
    fields_set: frozenset[str]


@dataclass(frozen=True)
class TagListFilters:
    offset: int = 0
    limit: int = 50
    is_active: bool | None = None
