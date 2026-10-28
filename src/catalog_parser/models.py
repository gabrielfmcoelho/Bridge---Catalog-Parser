"""Schema of catalog/dependencies.yml (pydantic). Rules that need more than the shape of the
data (reciprocity, "component must exist", ...) live in lint.py."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SLUG = r"^[a-z0-9][a-z0-9-]*$"


class Category(StrEnum):
    SERVICE = "service"
    DATA = "data"
    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"


class Criticality(StrEnum):
    HIGH = "high"      # dependents stop
    MEDIUM = "medium"  # dependents degrade (stale data, partial function)
    LOW = "low"        # observability / convenience


class Protocol(StrEnum):
    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"
    GRPC = "grpc"
    SSH = "ssh"


class Technology(StrEnum):
    TRINO = "trino"
    MINIO = "minio"
    HIVE_METASTORE = "hive-metastore"
    OPA = "opa"
    ORACLE = "oracle"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    REDIS = "redis"
    AIRFLOW = "airflow"
    CELERY = "celery"
    DBT = "dbt"
    ICEBERG = "iceberg"
    GITLAB = "gitlab"
    KEYCLOAK = "keycloak"
    SSRS = "ssrs"
    REST_API = "rest-api"
    OPENAI_API = "openai-api"
    OTEL_COLLECTOR = "otel-collector"


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
    type: Literal["gitlab"]
    host: str = Field(min_length=1)
    path: str = Field(min_length=1)


class Component(_Model):
    name: str = Field(pattern=SLUG)
    category: Category
    technology: Technology
    protocol: Protocol | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    criticality: Criticality
    description: str = Field(min_length=1)


class Dependency(_Model):
    """One end of a link. `ci` + `component` = the OTHER end; `local_component` = this CI's end.
    External systems (no catalog of their own) carry the traits inline instead of `component`."""

    ci: str = Field(pattern=SLUG)
    component: str | None = Field(default=None, pattern=SLUG)
    local_component: str | None = Field(default=None, pattern=SLUG)
    via: str | None = Field(default=None, pattern=SLUG)
    # inline traits — external systems only
    category: Category | None = None
    technology: Technology | None = None
    protocol: Protocol | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    criticality: Criticality | None = None
    description: str | None = Field(default=None, min_length=1)


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
