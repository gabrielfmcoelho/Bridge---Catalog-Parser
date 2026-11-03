"""Schema of a dependencies catalog (pydantic). Rules that need more than the shape of the data
(reciprocity, "component must exist", ...) live in rules/.

Terms such as `technology` or `criticality` are plain strings checked against the `Vocabulary`
passed in the validation context (`model_validate(data, context={"vocabulary": ...})`), so each
project decides its own values; without a context the default vocabulary applies."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from .config import Vocabulary

SLUG = r"^[a-z0-9][a-z0-9-]*$"
DEFAULT_VOCABULARY = Vocabulary()


def vocabulary_of(info: ValidationInfo) -> Vocabulary:
    return (info.context or {}).get("vocabulary") or DEFAULT_VOCABULARY


def _in_vocabulary(value: str | None, info: ValidationInfo) -> str | None:
    return value if value is None else vocabulary_of(info).check(info.field_name, value)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Owner(_Model):
    name: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=1)


class Entity(_Model):
    name: str = Field(min_length=1)
    slug: str = Field(pattern=SLUG)
    type: str = Field(min_length=1)


class Git(_Model):
    type: str = Field(min_length=1)  # provider: github, gitlab, ... (vocabulary.git_providers)
    host: str = Field(min_length=1)
    path: str = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def _provider(cls, value: str, info: ValidationInfo) -> str:
        return vocabulary_of(info).check("git_provider", value)


class Component(_Model):
    name: str = Field(pattern=SLUG)
    category: str
    technology: str = Field(min_length=1)
    protocol: str | None = Field(default=None, min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    criticality: str
    description: str = Field(min_length=1)

    _terms = field_validator("category", "technology", "protocol", "criticality")(_in_vocabulary)


class Dependency(_Model):
    """One end of a link. `ci` + `component` = the OTHER end; `local_component` = this CI's end.
    External systems (no catalog of their own) carry the traits inline instead of `component`."""

    ci: str = Field(pattern=SLUG)
    component: str | None = Field(default=None, pattern=SLUG)
    local_component: str | None = Field(default=None, pattern=SLUG)
    via: str | None = Field(default=None, pattern=SLUG)
    # inline traits — external systems only
    category: str | None = None
    technology: str | None = Field(default=None, min_length=1)
    protocol: str | None = Field(default=None, min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    criticality: str | None = None
    description: str | None = Field(default=None, min_length=1)

    _terms = field_validator("category", "technology", "protocol", "criticality")(_in_vocabulary)


class Dependencies(_Model):
    upstream: list[Dependency] = Field(default_factory=list)
    downstream: list[Dependency] = Field(default_factory=list)


class DependencyCatalog(_Model):
    ci: str = Field(pattern=SLUG)
    description: str = Field(min_length=1)
    owners: list[Owner] = Field(min_length=1)
    entity: list[Entity] = Field(min_length=1)
    git: Git
    components: list[Component] = Field(default_factory=list)
    dependencies: Dependencies
