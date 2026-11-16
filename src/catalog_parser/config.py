"""Settings: every project-specific value (vocabularies, schema rules, folder layout, enabled rules, diagram look).

Read from `.catalog-parser.toml`, from the `[tool.catalog-parser]` table of `pyproject.toml`, or
from a URL (`remote.py`) when the rules live in a central configuration repository. Config files
may also inherit from one or more base configs (`extends = "https://..."` or `extends = ["./base.toml"]`),
and a central config can lock sections (`locked = ["vocabulary", "schema"]`) so downstream
repositories cannot weaken organization-wide rules.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .dotenv import catalog_env
from .issues import Severity
from .remote import (
    AUTH_HEADER_ENV,
    CACHE_DIR_ENV,
    CACHE_TTL_ENV,
    TOKEN_ENV,
    RemoteCache,
    RemoteConfigLoader,
    RemoteError,
    is_url,
    resolve_location,
)

CONFIG_ENV = "CATALOG_PARSER_CONFIG"  # path or URL of a config file, used when none is given explicitly
CONFIG_FILE = ".catalog-parser.toml"
PYPROJECT = "pyproject.toml"
PYPROJECT_TABLE = "catalog-parser"    # [tool.catalog-parser]


class ConfigError(ValueError):
    """Invalid or unreadable configuration."""


def _strings(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"'{key}' must be a list of non-empty strings")
    return tuple(value)


def _string(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"'{key}' must be a non-empty string")
    return value


def _bool(value: Any, key: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be a boolean")
    return value


def _table(data: Mapping, name: str, keys: set[str]) -> Mapping:
    table = data.get(name, {})
    if not isinstance(table, Mapping):
        raise ConfigError(f"[{name}] must be a table")
    unknown = set(table) - keys
    if unknown:
        raise ConfigError(f"unknown key(s) in [{name}]: {', '.join(sorted(unknown))}")
    return table


@dataclass(frozen=True)
class Vocabulary:
    """Allowed values of the catalog's terms. `None` means open: any value is accepted."""

    technologies: frozenset[str] | None = None
    protocols: frozenset[str] | None = None
    git_providers: frozenset[str] | None = None
    entity_types: frozenset[str] | None = None
    categories: frozenset[str] = frozenset({"service", "data", "infrastructure", "application"})
    data_categories: frozenset[str] = frozenset({"data"})  # stored data, not a running service (W202, cylinders)
    criticalities: tuple[str, ...] = ("high", "medium", "low")  # most critical first
    custom: Mapping[str, frozenset[str]] = field(default_factory=dict)

    _SETS = ("technologies", "protocols", "git_providers", "entity_types", "categories", "data_categories")

    def __post_init__(self) -> None:
        if not self.criticalities:
            raise ConfigError("'vocabulary.criticalities' cannot be empty")
        stray = self.data_categories - self.categories
        if stray:
            raise ConfigError(f"'vocabulary.data_categories' not in categories: {', '.join(sorted(stray))}")

    @classmethod
    def from_mapping(cls, table: Mapping) -> Vocabulary:
        kw: dict[str, Any] = {k: frozenset(_strings(table[k], f"vocabulary.{k}")) for k in cls._SETS if k in table}
        if "criticalities" in table:
            kw["criticalities"] = _strings(table["criticalities"], "vocabulary.criticalities")
        if "custom" in table:
            custom_tbl = table["custom"]
            if not isinstance(custom_tbl, Mapping):
                raise ConfigError("[vocabulary.custom] must be a table")
            kw["custom"] = {k: frozenset(_strings(v, f"vocabulary.custom.{k}")) for k, v in custom_tbl.items()}
        return cls(**kw)

    def allowed(self, term: str) -> frozenset[str] | tuple[str, ...] | None:
        """Allowed values of `term` (category, technology, protocol, criticality, git_provider, entity_type, or custom)."""
        builtins: dict[str, frozenset[str] | tuple[str, ...] | None] = {
            "category": self.categories,
            "technology": self.technologies,
            "protocol": self.protocols,
            "criticality": self.criticalities,
            "git_provider": self.git_providers,
            "entity_type": self.entity_types,
        }
        if term in builtins:
            return builtins[term]
        if term in self.custom:
            return self.custom[term]
        raise KeyError(term)

    def check(self, term: str, value: str) -> str:
        allowed = self.allowed(term)
        if allowed is not None and value not in allowed:
            options = allowed if isinstance(allowed, tuple) else sorted(allowed)
            raise ValueError(f"{term} '{value}' is not one of: {', '.join(options)}")
        return value

    def is_data(self, category: str | None) -> bool:
        return category in self.data_categories


DEFAULT_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
DEFAULT_REQUIRED_FIELDS = frozenset({"owners", "entity", "git"})
ALLOWED_REQUIRED_FIELDS = frozenset({"owners", "entity", "git", "components"})
DEFAULT_EXTERNAL_REQUIRED = ("category", "technology", "criticality", "description")
ALLOWED_EXTERNAL_TRAITS = frozenset({"category", "technology", "protocol", "port", "criticality", "description"})


@dataclass(frozen=True)
class SchemaSettings:
    """Structural and schema-level policies configurable by an organization."""

    slug_pattern: str = DEFAULT_SLUG_PATTERN
    required_fields: frozenset[str] = DEFAULT_REQUIRED_FIELDS
    external_required_traits: tuple[str, ...] = DEFAULT_EXTERNAL_REQUIRED
    required_metadata: frozenset[str] = frozenset()
    allow_extra_fields: bool = False

    def __post_init__(self) -> None:
        try:
            re.compile(self.slug_pattern)
        except re.error as e:
            raise ConfigError(f"invalid regex in 'schema.slug_pattern': {e}") from e
        unknown_fields = self.required_fields - ALLOWED_REQUIRED_FIELDS
        if unknown_fields:
            raise ConfigError(
                f"unknown field(s) in 'schema.required_fields': {', '.join(sorted(unknown_fields))} "
                f"(allowed: {', '.join(sorted(ALLOWED_REQUIRED_FIELDS))})"
            )
        unknown_traits = set(self.external_required_traits) - ALLOWED_EXTERNAL_TRAITS
        if unknown_traits:
            raise ConfigError(
                f"unknown trait(s) in 'schema.external_required_traits': {', '.join(sorted(unknown_traits))}"
            )

    @classmethod
    def from_mapping(cls, table: Mapping) -> SchemaSettings:
        kw: dict[str, Any] = {}
        if "slug_pattern" in table:
            kw["slug_pattern"] = _string(table["slug_pattern"], "schema.slug_pattern")
        if "required_fields" in table:
            kw["required_fields"] = frozenset(_strings(table["required_fields"], "schema.required_fields"))
        if "external_required_traits" in table:
            kw["external_required_traits"] = _strings(
                table["external_required_traits"], "schema.external_required_traits"
            )
        if "required_metadata" in table:
            kw["required_metadata"] = frozenset(_strings(table["required_metadata"], "schema.required_metadata"))
        if "allow_extra_fields" in table:
            kw["allow_extra_fields"] = _bool(table["allow_extra_fields"], "schema.allow_extra_fields")
        return cls(**kw)


DEFAULT_SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build", "target"})


@dataclass(frozen=True)
class Layout:
    """Where catalogs live inside a repository and how peers are found."""

    catalog_dir: str = "catalog"          # relative to the repository root; may be nested (".meta/catalog")
    peers_env: str = "CATALOG_PEERS"      # os.pathsep-separated peers, used when none are given
    skip_dirs: frozenset[str] = DEFAULT_SKIP_DIRS
    peers: tuple[str, ...] = ()           # configured peer paths or remote URLs

    @classmethod
    def from_mapping(cls, table: Mapping, base_source: str | Path | None = None) -> Layout:
        kw: dict[str, Any] = {k: _string(table[k], f"layout.{k}") for k in ("catalog_dir", "peers_env") if k in table}
        if "skip_dirs" in table:
            kw["skip_dirs"] = frozenset(_strings(table["skip_dirs"], "layout.skip_dirs"))
        if "peers" in table:
            raw_peers = _strings(table["peers"], "layout.peers")
            if base_source is not None:
                kw["peers"] = tuple(str(resolve_location(base_source, p)) for p in raw_peers)
            else:
                kw["peers"] = raw_peers
        return cls(**kw)

    @property
    def depth(self) -> int:
        """Folders between the repository root and a catalog file."""
        return len(Path(self.catalog_dir).parts)


@dataclass(frozen=True)
class RuleSelection:
    """Which finding codes are reported, custom severity overrides, and rule plugins."""

    select: frozenset[str] = frozenset()  # empty = every code
    ignore: frozenset[str] = frozenset()
    severity: Mapping[str, Severity] = field(default_factory=dict)
    plugins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized: dict[str, Severity] = {}
        for code, sev in self.severity.items():
            if not isinstance(code, str) or not code:
                raise ConfigError("keys in [rules.severity] must be non-empty rule codes")
            try:
                normalized[code] = Severity(sev)
            except ValueError as e:
                allowed = ", ".join(s.value for s in Severity)
                raise ConfigError(f"invalid severity '{sev}' for rule '{code}': must be one of {allowed}") from e
        object.__setattr__(self, "severity", normalized)

    @classmethod
    def from_mapping(cls, table: Mapping) -> RuleSelection:
        kw: dict[str, Any] = {
            k: frozenset(_strings(table[k], f"rules.{k}")) for k in ("select", "ignore") if k in table
        }
        if "severity" in table:
            sev_table = table["severity"]
            if not isinstance(sev_table, Mapping):
                raise ConfigError("[rules.severity] must be a table mapping rule codes to 'error' or 'warning'")
            kw["severity"] = dict(sev_table)
        if "plugins" in table:
            kw["plugins"] = _strings(table["plugins"], "rules.plugins")
        return cls(**kw)

    def enabled(self, code: str) -> bool:
        def matches(patterns: frozenset[str]) -> bool:
            return any(code.startswith(p) for p in patterns)
        return (not self.select or matches(self.select)) and not matches(self.ignore)

    def severity_of(self, code: str, default: Severity) -> Severity:
        return self.severity.get(code, default)


DEFAULT_STYLES = {
    "high": "fill:#f8d7da,stroke:#c0392b,color:#000",
    "medium": "fill:#fff3cd,stroke:#b7950b,color:#000",
    "low": "fill:#d4edda,stroke:#1e8449,color:#000",
}
DEFAULT_TITLE = "Dependency map — {ci}"
DEFAULT_LEGEND = """\
`A --> B` means *A depends on B*. The label is the provider's protocol and port; `via X` marks indirect access.
Colour is the component's criticality (red high, yellow medium, green low). Cylinders are data components;
rounded boxes outside the repository box are external systems or consumers without a catalog."""
DIRECTIONS = ("LR", "RL", "TB", "TD", "BT")


@dataclass(frozen=True)
class DiagramSettings:
    """Where the Mermaid map is written and how it looks."""

    docs_dir: str = "docs"
    subdir: str = "catalog"  # generated files live in <docs_dir>/<subdir>/, never loose in docs
    filename: str = "dependencies.md"
    direction: str = "LR"
    title: str = DEFAULT_TITLE    # `{ci}` is replaced by the CI name
    legend: str = DEFAULT_LEGEND  # markdown printed under the diagram
    styles: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_STYLES))  # criticality -> classDef

    _STRINGS = ("docs_dir", "subdir", "filename", "direction", "title", "legend")

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ConfigError(f"'diagram.direction' must be one of: {', '.join(DIRECTIONS)}")

    @classmethod
    def from_mapping(cls, table: Mapping) -> DiagramSettings:
        kw: dict[str, Any] = {k: _string(table[k], f"diagram.{k}") for k in cls._STRINGS if k in table}
        if "styles" in table:
            styles = table["styles"]
            if not isinstance(styles, Mapping) or not all(isinstance(v, str) for v in styles.values()):
                raise ConfigError("[diagram.styles] must map criticality names to Mermaid classDef strings")
            kw["styles"] = dict(styles)
        return cls(**kw)


def _parse_extends(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    if isinstance(value, list | tuple) and all(isinstance(v, str) and v for v in value):
        return tuple(value)
    raise ConfigError("'extends' must be a non-empty string or list of non-empty strings")


def _merge_section_dicts(base: Mapping[str, Any], child: Mapping[str, Any], section: str) -> dict[str, Any]:
    merged = dict(base)
    for k, v in child.items():
        if isinstance(v, Mapping) and isinstance(merged.get(k), Mapping):
            merged[k] = {**merged[k], **v}
        elif section == "rules" and k in ("ignore", "plugins") and k in merged:
            prev = _strings(merged[k], f"rules.{k}")
            curr = _strings(v, f"rules.{k}")
            merged[k] = list(dict.fromkeys([*prev, *curr]))
        else:
            merged[k] = v
    return merged


@dataclass(frozen=True)
class Settings:
    vocabulary: Vocabulary = field(default_factory=Vocabulary)
    schema: SchemaSettings = field(default_factory=SchemaSettings)
    layout: Layout = field(default_factory=Layout)
    rules: RuleSelection = field(default_factory=RuleSelection)
    diagram: DiagramSettings = field(default_factory=DiagramSettings)
    source: Path | str | None = None  # file or URL the settings were read from, None for the defaults
    locked: frozenset[str] = frozenset()

    _SECTIONS = {
        "vocabulary": (
            Vocabulary,
            {"technologies", "protocols", "git_providers", "entity_types", "categories", "data_categories",
             "criticalities", "custom"},
        ),
        "schema": (
            SchemaSettings,
            {"slug_pattern", "required_fields", "external_required_traits", "required_metadata", "allow_extra_fields"},
        ),
        "layout": (Layout, {"catalog_dir", "peers_env", "skip_dirs", "peers"}),
        "rules": (RuleSelection, {"select", "ignore", "severity", "plugins"}),
        "diagram": (DiagramSettings, {"docs_dir", "subdir", "filename", "direction", "title", "legend", "styles"}),
    }
    _META_KEYS = {"extends", "locked"}

    @classmethod
    def _validate_raw_mapping(cls, data: Mapping) -> tuple[tuple[str, ...], frozenset[str]]:
        unknown = set(data) - set(cls._SECTIONS) - cls._META_KEYS
        if unknown:
            raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
        extends = _parse_extends(data["extends"]) if "extends" in data else ()
        locked: frozenset[str] = frozenset()
        if "locked" in data:
            locked = frozenset(_strings(data["locked"], "locked"))
            bad_locked = locked - set(cls._SECTIONS)
            if bad_locked:
                raise ConfigError(f"unknown section(s) in 'locked': {', '.join(sorted(bad_locked))}")
        for name, (_, keys) in cls._SECTIONS.items():
            _table(data, name, keys)
        return extends, locked

    @classmethod
    def _resolve_raw(
        cls,
        data: Mapping,
        source: Path | str | None,
        loader: RemoteConfigLoader | None,
        stack: tuple[str, ...],
    ) -> tuple[dict[str, dict[str, Any]], frozenset[str], dict[str, str]]:
        extends, own_locked = cls._validate_raw_mapping(data)
        merged_sections: dict[str, dict[str, Any]] = {name: {} for name in cls._SECTIONS}
        locked_by: dict[str, str] = {}

        for parent_ref in extends:
            parent_loc = resolve_location(source, parent_ref)
            canonical = str(parent_loc)
            if canonical in stack:
                chain = " -> ".join([*stack, canonical])
                raise ConfigError(f"circular config 'extends': {chain}")
            parent_data = cls._read_raw_location(parent_loc, loader)
            parent_sections, _, parent_locked_by = cls._resolve_raw(
                parent_data, parent_loc, loader, (*stack, canonical)
            )
            for sec_name, sec_dict in parent_sections.items():
                if sec_dict:
                    if sec_name in locked_by:
                        raise ConfigError(
                            f"section [{sec_name}] is locked by {locked_by[sec_name]} and cannot be overridden"
                        )
                    merged_sections[sec_name] = _merge_section_dicts(merged_sections[sec_name], sec_dict, sec_name)
            locked_by.update(parent_locked_by)

        for sec_name in cls._SECTIONS:
            if sec_name in data:
                if sec_name in locked_by:
                    raise ConfigError(
                        f"section [{sec_name}] is locked by {locked_by[sec_name]} and cannot be overridden"
                    )
                child_table = dict(data[sec_name])
                if sec_name == "layout" and "peers" in child_table and source is not None:
                    raw_peers = _strings(child_table["peers"], "layout.peers")
                    child_table["peers"] = [str(resolve_location(source, p)) for p in raw_peers]
                merged_sections[sec_name] = _merge_section_dicts(merged_sections[sec_name], child_table, sec_name)

        source_label = str(source or "<config>")
        for sec_name in own_locked:
            locked_by.setdefault(sec_name, source_label)

        return merged_sections, frozenset(locked_by), locked_by

    @classmethod
    def _read_raw_location(cls, location: str | Path, loader: RemoteConfigLoader | None) -> Mapping:
        if is_url(location):
            try:
                text, name = (loader or RemoteConfigLoader()).read(str(location))
            except RemoteError as e:
                raise ConfigError(str(e)) from None
            return cls._parse_toml(text, name, location)
        path = Path(location)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"cannot read config {path}: {e}") from e
        return cls._parse_toml(text, path.name, path)

    @classmethod
    def _parse_toml(cls, text: str, name: str, source: Path | str | None) -> Mapping:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"cannot read config {source}: {e}") from e
        if name == PYPROJECT:
            data = data.get("tool", {}).get(PYPROJECT_TABLE, {})
        if not isinstance(data, Mapping):
            raise ConfigError(f"{source}: config root must be a table")
        return data

    @classmethod
    def from_mapping(
        cls,
        data: Mapping,
        source: Path | str | None = None,
        loader: RemoteConfigLoader | None = None,
    ) -> Settings:
        stack = (str(source),) if source is not None else ()
        merged_sections, all_locked, _ = cls._resolve_raw(data, source, loader, stack)
        kw: dict[str, Any] = {}
        for name, (model, _) in cls._SECTIONS.items():
            kw[name] = model.from_mapping(merged_sections[name])
        return cls(**kw, source=source, locked=all_locked)

    @classmethod
    def from_text(
        cls,
        text: str,
        name: str,
        source: Path | str | None = None,
        loader: RemoteConfigLoader | None = None,
    ) -> Settings:
        """TOML of a `.catalog-parser.toml` (the whole file) or of a `pyproject.toml` (its
        [tool.catalog-parser] table, told apart by `name`)."""
        data = cls._parse_toml(text, name, source)
        try:
            return cls.from_mapping(data, source=source, loader=loader)
        except ConfigError as e:
            msg = str(e)
            if source is not None and not msg.startswith(str(source)):
                raise ConfigError(f"{source}: {msg}") from e
            raise

    @classmethod
    def from_file(cls, path: str | Path, loader: RemoteConfigLoader | None = None) -> Settings:
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"cannot read config {path}: {e}") from e
        return cls.from_text(text, path.name, source=path, loader=loader)

    @classmethod
    def from_url(cls, url: str, loader: RemoteConfigLoader | None = None) -> Settings:
        """A config served over HTTPS, e.g. a GitLab/GitHub file page (see remote.py); token in $CATALOG_PARSER_TOKEN."""
        active_loader = loader or RemoteConfigLoader()
        try:
            text, name = active_loader.read(url)
        except RemoteError as e:
            raise ConfigError(str(e)) from None
        return cls.from_text(text, name, source=url, loader=active_loader)

    @classmethod
    def load(cls, location: str | Path, loader: RemoteConfigLoader | None = None) -> Settings:
        """A config file path or URL."""
        return cls.from_url(str(location), loader) if is_url(location) else cls.from_file(location, loader)

    @classmethod
    def discover(cls, start: str | Path = ".") -> Settings:
        """$CATALOG_PARSER_CONFIG (path or URL), else the nearest config file from `start` up to the
        repository boundary (a folder with `.git`), else the defaults. See `resolve`."""
        return cls.resolve(None, start)

    @classmethod
    def resolve(cls, config: str | Path | None = None, start: str | Path = ".") -> Settings:
        """`config` (path or URL) when given, else `discover`'s order. $CATALOG_PARSER_CONFIG and
        $CATALOG_PARSER_TOKEN come from the environment or from the `.env` found from `start` (dotenv.py)."""
        env = catalog_env(start)
        raw_ttl = env.get(CACHE_TTL_ENV, "0")
        try:
            ttl = float(raw_ttl)
        except ValueError:
            ttl = 0.0
        cache = RemoteCache(ttl=ttl, directory=env.get(CACHE_DIR_ENV))
        loader = RemoteConfigLoader(
            token=env.get(TOKEN_ENV, ""),
            auth_header=env.get(AUTH_HEADER_ENV),
            cache=cache,
        )
        location = config or env.get(CONFIG_ENV)
        if location:
            return cls.load(location, loader)
        found = find_config(start)
        return cls.from_file(found, loader=loader) if found else cls()

    def with_rules(self, select: frozenset[str] | None = None, ignore: frozenset[str] = frozenset()) -> Settings:
        """`select` replaces the configured selection; `ignore` adds to it."""
        rules = replace(
            self.rules,
            select=self.rules.select if select is None else select,
            ignore=self.rules.ignore | ignore,
        )
        return replace(self, rules=rules)

    def with_diagram(self, **overrides: str | None) -> Settings:
        """Override diagram settings, ignoring the ones that are None."""
        given = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, diagram=replace(self.diagram, **given)) if given else self


def find_config(start: str | Path = ".") -> Path | None:
    here = Path(start).resolve()
    if not here.is_dir():
        here = here.parent
    for folder in (here, *here.parents):
        candidate = folder / CONFIG_FILE
        if candidate.is_file():
            return candidate
        pyproject = folder / PYPROJECT
        if pyproject.is_file() and _has_table(pyproject):
            return pyproject
        if (folder / ".git").exists():
            return None
    return None


def _has_table(pyproject: Path) -> bool:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return PYPROJECT_TABLE in data.get("tool", {})
