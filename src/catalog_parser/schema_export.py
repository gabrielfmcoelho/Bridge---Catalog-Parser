"""JSON Schema generation for `dependencies.yml` and `.catalog-parser.toml`.

When `Settings` are provided (e.g. from a remote governance repository), `export_catalog_schema`
injects the organization's closed vocabularies (`enum`), `slug_pattern`, `required_fields`, and
`required_metadata` directly into the generated JSON Schema so IDEs (VS Code, IntelliJ, Neovim)
provide organization-aware autocomplete and validation.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from .config import ALLOWED_EXTERNAL_TRAITS, ALLOWED_REQUIRED_FIELDS, DIRECTIONS, Settings
from .issues import Severity
from .models import DependencyCatalog


def _inject_enum(prop: dict[str, Any], values: frozenset[str] | tuple[str, ...] | None) -> None:
    if values is None:
        return
    enum_list = list(values) if isinstance(values, tuple) else sorted(values)
    if "anyOf" in prop:
        for branch in prop["anyOf"]:
            if branch.get("type") == "string":
                branch["enum"] = enum_list
    else:
        prop["enum"] = enum_list


def export_catalog_schema(settings: Settings | None = None) -> dict[str, Any]:
    """Generate a JSON Schema for `dependencies.yml` tailored to `settings`."""
    cfg = settings or Settings()
    vocab = cfg.vocabulary
    sch = cfg.schema

    schema = copy.deepcopy(DependencyCatalog.model_json_schema())
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "DependencyCatalog"

    defs = schema.get("$defs", {})

    # Apply slug_pattern
    for prop_name in ("ci",):
        if prop_name in schema.get("properties", {}):
            schema["properties"][prop_name]["pattern"] = sch.slug_pattern

    if "Entity" in defs:
        entity_props = defs["Entity"].get("properties", {})
        if "slug" in entity_props:
            entity_props["slug"]["pattern"] = sch.slug_pattern
        if "type" in entity_props:
            _inject_enum(entity_props["type"], vocab.entity_types)

    if "Git" in defs:
        git_props = defs["Git"].get("properties", {})
        if "type" in git_props:
            _inject_enum(git_props["type"], vocab.git_providers)

    for def_name in ("Component", "Dependency"):
        if def_name in defs:
            d_props = defs[def_name].get("properties", {})
            for slug_field in ("name", "ci", "component", "local_component", "via"):
                if slug_field in d_props:
                    target = d_props[slug_field]
                    if "anyOf" in target:
                        for branch in target["anyOf"]:
                            if branch.get("type") == "string":
                                branch["pattern"] = sch.slug_pattern
                    else:
                        target["pattern"] = sch.slug_pattern
            for term in ("category", "technology", "protocol", "criticality"):
                if term in d_props:
                    _inject_enum(d_props[term], vocab.allowed(term))

    # Apply required_fields at top level
    base_required = {"ci", "description", "dependencies"} | set(sch.required_fields)
    if sch.required_metadata:
        base_required.add("metadata")
        meta_prop = schema.get("properties", {}).get("metadata", {})
        meta_prop["required"] = sorted(sch.required_metadata)
    schema["required"] = sorted(base_required)

    if sch.allow_extra_fields:
        schema["additionalProperties"] = True
        for d in defs.values():
            if isinstance(d, dict) and d.get("type") == "object":
                d["additionalProperties"] = True

    return schema


def export_config_schema() -> dict[str, Any]:
    """Generate a JSON Schema for `.catalog-parser.toml`."""
    section_names = ["vocabulary", "schema", "layout", "rules", "diagram"]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "CatalogParserConfig",
        "description": "Configuration schema for .catalog-parser.toml and [tool.catalog-parser].",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "extends": {
                "description": "Parent config URL(s) or relative path(s) to inherit from.",
                "oneOf": [
                    {"type": "string", "minLength": 1},
                    {"type": "array", "items": {"type": "string", "minLength": 1}},
                ],
            },
            "locked": {
                "description": "Sections locked by this config so child configs cannot override them.",
                "type": "array",
                "items": {"type": "string", "enum": section_names},
            },
            "vocabulary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "technologies": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "protocols": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "git_providers": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "entity_types": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "categories": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "data_categories": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "criticalities": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
                    "custom": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "slug_pattern": {"type": "string", "minLength": 1},
                    "required_fields": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(ALLOWED_REQUIRED_FIELDS)},
                    },
                    "external_required_traits": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(ALLOWED_EXTERNAL_TRAITS)},
                    },
                    "required_metadata": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "allow_extra_fields": {"type": "boolean"},
                },
            },
            "layout": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "catalog_dir": {"type": "string", "minLength": 1},
                    "peers_env": {"type": "string", "minLength": 1},
                    "skip_dirs": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "peers": {"type": "array", "items": {"type": "string", "minLength": 1}},
                },
            },
            "rules": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "select": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "ignore": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "plugins": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "severity": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "string",
                            "enum": [s.value for s in Severity],
                        },
                    },
                },
            },
            "diagram": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "docs_dir": {"type": "string", "minLength": 1},
                    "subdir": {"type": "string", "minLength": 1},
                    "filename": {"type": "string", "minLength": 1},
                    "direction": {"type": "string", "enum": list(DIRECTIONS)},
                    "title": {"type": "string", "minLength": 1},
                    "legend": {"type": "string", "minLength": 1},
                    "styles": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        },
    }


def dump_schema(target: str = "catalog", settings: Settings | None = None) -> str:
    """Return formatted JSON Schema string for `'catalog'` or `'config'`."""
    if target == "config":
        data = export_config_schema()
    elif target == "catalog":
        data = export_catalog_schema(settings)
    else:
        raise ValueError(f"unknown schema target '{target}' (expected 'catalog' or 'config')")
    return json.dumps(data, indent=2, ensure_ascii=False)
