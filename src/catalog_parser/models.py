"""Schema of a dependencies catalog (pydantic). Rules that need more than the shape of the data
(reciprocity, "component must exist", ...) live in rules/.

Terms such as `technology` or `criticality` are plain strings checked against the `Vocabulary`
passed in the validation context (`model_validate(data, context={"vocabulary": ..., "schema": ...})`),
and structural requirements (`slug_pattern`, `required_fields`, `required_metadata`,
`allow_extra_fields`) are checked against `SchemaSettings`, so each organization decides its own
policies; without a context the defaults apply."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from .config import DEFAULT_SLUG_PATTERN, SchemaSettings, Vocabulary

SLUG = DEFAULT_SLUG_PATTERN
DEFAULT_VOCABULARY = Vocabulary()
DEFAULT_SCHEMA = SchemaSettings()


def vocabulary_of(info: ValidationInfo) -> Vocabulary:
    return (info.context or {}).get("vocabulary") or DEFAULT_VOCABULARY


def schema_of(info: ValidationInfo) -> SchemaSettings:
    return (info.context or {}).get("schema") or DEFAULT_SCHEMA


def _in_vocabulary(value: str | None, info: ValidationInfo) -> str | None:
    return value if value is None else vocabulary_of(info).check(info.field_name, value)


def _is_slug(value: str | None, info: ValidationInfo) -> str | None:
    if value is None:
        return None
    pattern = schema_of(info).slug_pattern
    if not re.fullmatch(pattern, value):
        raise ValueError(f"String should match pattern '{pattern}'")
    return value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _filter_extra_if_allowed(cls, data: Any, info: ValidationInfo) -> Any:
        if isinstance(data, dict) and schema_of(info).allow_extra_fields:
            return {k: v for k, v in data.items() if k in cls.model_fields}
        return data


class Owner(_Model):
    name: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=1)


class Entity(_Model):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    type: str = Field(min_length=1)

    _slug = field_validator("slug")(_is_slug)

    @field_validator("type")
    @classmethod
    def _entity_type(cls, value: str, info: ValidationInfo) -> str:
        return vocabulary_of(info).check("entity_type", value)


class Git(_Model):
    type: str = Field(min_length=1)  # provider: github, gitlab, ... (vocabulary.git_providers)
    host: str = Field(min_length=1)
    path: str = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def _provider(cls, value: str, info: ValidationInfo) -> str:
        return vocabulary_of(info).check("git_provider", value)


class Component(_Model):
    name: str = Field(min_length=1)
    category: str
    technology: str = Field(min_length=1)
    protocol: str | None = Field(default=None, min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    criticality: str
    description: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _slug = field_validator("name")(_is_slug)
    _terms = field_validator("category", "technology", "protocol", "criticality")(_in_vocabulary)


class Dependency(_Model):
    """One end of a link. `ci` + `component` = the OTHER end; `local_component` = this CI's end.
    External systems (no catalog of their own) carry the traits inline instead of `component`."""

    ci: str = Field(min_length=1)
    component: str | None = Field(default=None)
    local_component: str | None = Field(default=None)
    via: str | None = Field(default=None)
    # inline traits — external systems only
    category: str | None = None
    technology: str | None = Field(default=None, min_length=1)
    protocol: str | None = Field(default=None, min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    criticality: str | None = None
    description: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _slugs = field_validator("ci", "component", "local_component", "via")(_is_slug)
    _terms = field_validator("category", "technology", "protocol", "criticality")(_in_vocabulary)


class Dependencies(_Model):
    upstream: list[Dependency] = Field(default_factory=list)
    downstream: list[Dependency] = Field(default_factory=list)


class DependencyCatalog(_Model):
    ci: str = Field(min_length=1)
    description: str = Field(min_length=1)
    owners: list[Owner] = Field(default_factory=list, validate_default=True)
    entity: list[Entity] = Field(default_factory=list, validate_default=True)
    git: Git | None = Field(default=None, validate_default=True)
    components: list[Component] = Field(default_factory=list, validate_default=True)
    dependencies: Dependencies
    metadata: dict[str, Any] = Field(default_factory=dict, validate_default=True)

    _slug = field_validator("ci")(_is_slug)

    @field_validator("owners", "entity", "components")
    @classmethod
    def _check_required_list(cls, value: list[Any], info: ValidationInfo) -> list[Any]:
        if info.field_name in schema_of(info).required_fields and not value:
            raise ValueError(f"'{info.field_name}' is required and cannot be empty")
        return value

    @field_validator("git")
    @classmethod
    def _check_required_git(cls, value: Git | None, info: ValidationInfo) -> Git | None:
        if "git" in schema_of(info).required_fields and value is None:
            raise ValueError("'git' is required")
        return value

    @field_validator("metadata")
    @classmethod
    def _check_required_metadata(cls, value: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        missing = sorted(schema_of(info).required_metadata - set(value))
        if missing:
            raise ValueError(f"missing required metadata key(s): {', '.join(missing)}")
        return value
