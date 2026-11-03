"""Parser, linter and diagram generator for service dependency catalogs (`catalog/*.yml`)."""

from .config import ConfigError, DiagramSettings, Layout, RuleSelection, Settings, Vocabulary
from .diagram import DiagramGenerator, DiagramResult, MarkdownRenderer, MermaidRenderer, generate_diagram, render_mermaid
from .discovery import CatalogDiscoverer
from .issues import Issue, RuleInfo, Severity
from .kinds import DEPENDENCIES, CatalogKind, KindRegistry, default_registry
from .linter import Linter, lint_cross, lint_file
from .models import DependencyCatalog
from .parser import CatalogParser, Parsed, parse_dependencies
from .reporters import REPORTERS, Reporter
from .repository import PeerLoader, Repository, RepositoryChecker, check_repo
from .rules import CrossRule, FileRule, Finding, Rule

__all__ = [
    "DEPENDENCIES", "REPORTERS", "CatalogDiscoverer", "CatalogKind", "CatalogParser", "ConfigError", "CrossRule",
    "DependencyCatalog", "DiagramGenerator", "DiagramResult", "DiagramSettings", "FileRule", "Finding", "Issue",
    "KindRegistry", "Layout", "Linter", "MarkdownRenderer", "MermaidRenderer", "Parsed", "PeerLoader", "Reporter",
    "Repository", "RepositoryChecker", "Rule", "RuleInfo", "RuleSelection", "Settings", "Severity", "Vocabulary",
    "check_repo", "default_registry", "generate_diagram", "lint_cross", "lint_file", "parse_dependencies",
    "render_mermaid",
]
