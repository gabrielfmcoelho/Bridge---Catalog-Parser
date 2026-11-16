"""Parser, linter and diagram generator for service dependency catalogs (`catalog/*.yml`)."""

from .config import ConfigError, DiagramSettings, Layout, RuleSelection, SchemaSettings, Settings, Vocabulary
from .diagram import (
    DiagramGenerator,
    DiagramResult,
    MarkdownRenderer,
    MermaidRenderer,
    generate_diagram,
    render_mermaid,
)
from .discovery import CatalogDiscoverer
from .issues import Issue, RuleInfo, Severity
from .kinds import DEPENDENCIES, CatalogKind, KindRegistry, default_registry
from .linter import Linter, lint_cross, lint_file
from .models import DependencyCatalog
from .parser import CatalogParser, Parsed, parse_dependencies
from .plugins import load_plugin_spec, load_plugins
from .remote import PROVIDERS, RemoteCache, RemoteConfigLoader, RemoteError, RemoteFile, RemoteProvider
from .reporters import REPORTERS, Reporter
from .repository import PeerLoader, Repository, RepositoryChecker, check_repo
from .rules import CrossRule, FileRule, Finding, Rule
from .schema_export import dump_schema, export_catalog_schema, export_config_schema

__all__ = [
    "DEPENDENCIES",
    "PROVIDERS",
    "REPORTERS",
    "CatalogDiscoverer",
    "CatalogKind",
    "CatalogParser",
    "ConfigError",
    "CrossRule",
    "DependencyCatalog",
    "DiagramGenerator",
    "DiagramResult",
    "DiagramSettings",
    "FileRule",
    "Finding",
    "Issue",
    "KindRegistry",
    "Layout",
    "Linter",
    "MarkdownRenderer",
    "MermaidRenderer",
    "Parsed",
    "PeerLoader",
    "RemoteCache",
    "RemoteConfigLoader",
    "RemoteError",
    "RemoteFile",
    "RemoteProvider",
    "Reporter",
    "Repository",
    "RepositoryChecker",
    "Rule",
    "RuleInfo",
    "RuleSelection",
    "SchemaSettings",
    "Settings",
    "Severity",
    "Vocabulary",
    "check_repo",
    "default_registry",
    "dump_schema",
    "export_catalog_schema",
    "export_config_schema",
    "generate_diagram",
    "lint_cross",
    "lint_file",
    "load_plugin_spec",
    "load_plugins",
    "parse_dependencies",
    "render_mermaid",
]
