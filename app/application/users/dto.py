from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateEditorData:
    email: str
    first_name: str
    last_name: str
    password: str = field(repr=False)
    created_by_admin_id: str


@dataclass(frozen=True)
class UpdateUserData:
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = field(default=None, repr=False)
