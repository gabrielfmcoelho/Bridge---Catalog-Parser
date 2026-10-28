"""Settings: every project-specific value (vocabularies, folder layout, enabled rules, diagram look).

Read from `.catalog-parser.toml` or from the `[tool.catalog-parser]` table of `pyproject.toml`.
Everything has a default, so a project without a config file works out of the box:

    [vocabulary]                  # omit a list to accept any value
    technologies = ["postgresql", "redis", "rest-api"]
    [layout]
    catalog_dir = "catalog"
    [rules]
    ignore = ["E110"]
    [diagram]
    direction = "TB"
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

CONFIG_ENV = "CATALOG_PARSER_CONFIG"  # path of a config file, used when none is given explicitly
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
    categories: frozenset[str] = frozenset({"service", "data", "infrastructure", "application"})
    data_categories: frozenset[str] = frozenset({"data"})  # stored data, not a running service (W202, cylinders)
    criticalities: tuple[str, ...] = ("high", "medium", "low")  # most critical first

    _SETS = ("technologies", "protocols", "git_providers", "categories", "data_categories")

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
        return cls(**kw)

    def allowed(self, term: str) -> frozenset[str] | tuple[str, ...] | None:
        """Allowed values of `term` (category, technology, protocol, criticality, git_provider)."""
        return {
            "category": self.categories,
            "technology": self.technologies,
            "protocol": self.protocols,
            "criticality": self.criticalities,
            "git_provider": self.git_providers,
        }[term]

    def check(self, term: str, value: str) -> str:
        allowed = self.allowed(term)
        if allowed is not None and value not in allowed:
            options = allowed if isinstance(allowed, tuple) else sorted(allowed)
            raise ValueError(f"{term} '{value}' is not one of: {', '.join(options)}")
        return value

    def is_data(self, category: str | None) -> bool:
        return category in self.data_categories


DEFAULT_SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build", "target"})


@dataclass(frozen=True)
class Layout:
    """Where catalogs live inside a repository and how peers are found."""

    catalog_dir: str = "catalog"          # relative to the repository root; may be nested (".meta/catalog")
    peers_env: str = "CATALOG_PEERS"      # os.pathsep-separated peers, used when none are given
    skip_dirs: frozenset[str] = DEFAULT_SKIP_DIRS

    @classmethod
    def from_mapping(cls, table: Mapping) -> Layout:
        kw: dict[str, Any] = {k: _string(table[k], f"layout.{k}") for k in ("catalog_dir", "peers_env") if k in table}
        if "skip_dirs" in table:
            kw["skip_dirs"] = frozenset(_strings(table["skip_dirs"], "layout.skip_dirs"))
        return cls(**kw)

    @property
    def depth(self) -> int:
        """Folders between the repository root and a catalog file."""
        return len(Path(self.catalog_dir).parts)


@dataclass(frozen=True)
class RuleSelection:
    """Which finding codes are reported. Entries match a code or a prefix of it ("E1", "X")."""

    select: frozenset[str] = frozenset()  # empty = every code
    ignore: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(cls, table: Mapping) -> RuleSelection:
        return cls(**{k: frozenset(_strings(table[k], f"rules.{k}")) for k in ("select", "ignore") if k in table})

    def enabled(self, code: str) -> bool:
        def matches(patterns: frozenset[str]) -> bool:
            return any(code.startswith(p) for p in patterns)
        return (not self.select or matches(self.select)) and not matches(self.ignore)


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


@dataclass(frozen=True)
class Settings:
    vocabulary: Vocabulary = field(default_factory=Vocabulary)
    layout: Layout = field(default_factory=Layout)
    rules: RuleSelection = field(default_factory=RuleSelection)
    diagram: DiagramSettings = field(default_factory=DiagramSettings)
    source: Path | None = None  # file the settings were read from, None for the defaults

    _SECTIONS = {
        "vocabulary": (Vocabulary, {"technologies", "protocols", "git_providers", "categories",
                                    "data_categories", "criticalities"}),
        "layout": (Layout, {"catalog_dir", "peers_env", "skip_dirs"}),
        "rules": (RuleSelection, {"select", "ignore"}),
        "diagram": (DiagramSettings, {"docs_dir", "subdir", "filename", "direction", "title", "legend", "styles"}),
    }

    @classmethod
    def from_mapping(cls, data: Mapping, source: Path | None = None) -> Settings:
        unknown = set(data) - set(cls._SECTIONS)
        if unknown:
            raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
        kw: dict[str, Any] = {name: model.from_mapping(_table(data, name, keys))
                              for name, (model, keys) in cls._SECTIONS.items()}
        return cls(**kw, source=source)

    @classmethod
    def from_file(cls, path: str | Path) -> Settings:
        """A `.catalog-parser.toml` (the whole file) or a `pyproject.toml` (its [tool.catalog-parser] table)."""
        path = Path(path)
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(f"cannot read config {path}: {e}") from e
        if path.name == PYPROJECT:
            data = data.get("tool", {}).get(PYPROJECT_TABLE, {})
        try:
            return cls.from_mapping(data, source=path)
        except ConfigError as e:
            raise ConfigError(f"{path}: {e}") from e

    @classmethod
    def discover(cls, start: str | Path = ".") -> Settings:
        """$CATALOG_PARSER_CONFIG, else the nearest config file from `start` up to the repository
        boundary (a folder with `.git`), else the defaults."""
        env = os.environ.get(CONFIG_ENV)
        if env:
            return cls.from_file(env)
        found = find_config(start)
        return cls.from_file(found) if found else cls()

    def with_rules(self, select: frozenset[str] | None = None, ignore: frozenset[str] = frozenset()) -> Settings:
        """`select` replaces the configured selection; `ignore` adds to it."""
        rules = RuleSelection(self.rules.select if select is None else select, self.rules.ignore | ignore)
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
