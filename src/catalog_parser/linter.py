"""Linter: parses catalog files and runs the enabled rules of their kind."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from .config import Settings
from .discovery import CatalogDiscoverer
from .issues import WARNING, Issue, RuleInfo, sort_issues
from .kinds import DEPENDENCIES, CatalogKind, KindRegistry, default_registry
from .parser import Parsed
from .rules.base import Rule

UNKNOWN_KIND = RuleInfo("W001", WARNING, "file name with no registered catalog kind")


class Linter:
    def __init__(self, settings: Settings | None = None, registry: KindRegistry | None = None,
                 discoverer: CatalogDiscoverer | None = None):
        self.settings = settings or Settings()
        self.registry = registry or default_registry()
        self.discoverer = discoverer or CatalogDiscoverer(self.settings.layout, self.registry.filenames)

    def _enabled(self, rules: Iterable[Rule]) -> list[Rule]:
        return [r for r in rules if self.settings.rules.enabled(r.code)]

    def kind_of(self, path: Path) -> CatalogKind | None:
        return self.registry.get(path.name)

    def lint_file(self, path: str | Path, kind: CatalogKind | None = None) -> Parsed:
        """Parse + single-file rules. Rules only run when the schema is valid. A file whose name is
        not registered is read as `kind`, or as a dependencies catalog when no kind is given."""
        path = Path(path)
        kind = kind or self.kind_of(path) or DEPENDENCIES
        parsed = kind.parser(self.settings.vocabulary).parse(path)
        parsed.issues = [i for i in parsed.issues if self.settings.rules.enabled(i.code)]
        if parsed.catalog is not None:
            for rule in self._enabled(kind.file_rules):
                for f in rule.check(parsed.catalog, self.settings.vocabulary):
                    parsed.issues.append(parsed.issue(rule.info.code, rule.info.severity, f.message, f.location, f.blame))
        return parsed

    def lint_cross(self, files: Sequence[Parsed], kind: CatalogKind | None = None) -> list[Issue]:
        """Rules that need several catalogs of the same kind at once."""
        issues: list[Issue] = []
        for rule in self._enabled((kind or DEPENDENCIES).cross_rules):
            for parsed, f in rule.check(files, self.settings.vocabulary):
                issues.append(parsed.issue(rule.info.code, rule.info.severity, f.message, f.location, f.blame))
        return issues

    def lint_paths(self, paths: Iterable[str | Path], cross: bool = True) -> list[Issue]:
        """Every catalog under `paths`, one by one and then across files of the same kind."""
        issues: list[Issue] = []
        by_kind: dict[str, list[Parsed]] = {}
        for f in self.discoverer.discover(paths):
            kind = self.kind_of(f)
            if kind is None:
                if self.settings.rules.enabled(UNKNOWN_KIND.code):
                    issues.append(Issue(UNKNOWN_KIND.code, UNKNOWN_KIND.severity, f"no schema registered for '{f.name}'", f))
                continue
            parsed = self.lint_file(f, kind)
            issues.extend(parsed.issues)
            by_kind.setdefault(kind.filename, []).append(parsed)
        if cross:
            for filename, files in by_kind.items():
                issues.extend(self.lint_cross(files, self.registry.get(filename)))
        return sort_issues(issues)


def lint_file(path: str | Path, settings: Settings | None = None) -> Parsed:
    """Lint one dependencies catalog (default settings unless given)."""
    return Linter(settings).lint_file(path, DEPENDENCIES)


def lint_cross(files: Sequence[Parsed], settings: Settings | None = None) -> list[Issue]:
    """Cross-file rules over dependencies catalogs. CIs absent from `files` are treated as external."""
    return Linter(settings).lint_cross(files, DEPENDENCIES)
