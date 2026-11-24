from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class PageTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["PAGE"]
    id: UUID


class ProjectTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["PROJECT"]
    id: UUID


class PostTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["POST"]
    id: UUID


LinkTarget: TypeAlias = Annotated[
    PageTarget | ProjectTarget | PostTarget,
    Field(discriminator="type"),
]


class HeroButton(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ]
    link_target: LinkTarget


class HeroBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: Literal["HERO"]
    headline: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ]
    subline: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=500),
    ] | None = None
    media_id: UUID | None = None
    button: HeroButton | None = None


class MarkdownBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: Literal["MARKDOWN"]
    body: str


class ProjectGridBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: Literal["PROJECT_GRID"]
    mode: Literal["FEATURED", "MANUAL"] = "FEATURED"
    project_ids: list[UUID] = Field(default_factory=list)
    limit: int = Field(default=3, ge=1, le=12)

    @model_validator(mode="after")
    def validate_mode(self) -> "ProjectGridBlock":
        if self.mode == "MANUAL" and not self.project_ids:
            raise ValueError("Manual project grids need at least one project.")
        if self.mode == "FEATURED" and self.project_ids:
            raise ValueError("Featured project grids cannot specify project IDs.")
        if len(set(self.project_ids)) != len(self.project_ids):
            raise ValueError("A project cannot appear more than once in a grid.")
        return self


SkillProficiency = Literal[
    "FAMILIAR",
    "WORKING",
    "PROFICIENT",
    "ADVANCED",
    "EXPERT",
]


class SkillEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    proficiency: SkillProficiency


class SkillsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    type: Literal["SKILLS"]
    heading: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    description: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=300),
    ] | None = None
    skills: list[SkillEntry] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_skills(self) -> "SkillsBlock":
        skill_ids = [skill.id for skill in self.skills]
        skill_names = [skill.name.casefold() for skill in self.skills]
        if len(set(skill_ids)) != len(skill_ids):
            raise ValueError("Skill IDs must be unique.")
        if len(set(skill_names)) != len(skill_names):
            raise ValueError("Skill names must be unique.")
        return self


PageBlock: TypeAlias = Annotated[
    HeroBlock | MarkdownBlock | ProjectGridBlock | SkillsBlock,
    Field(discriminator="type"),
]
