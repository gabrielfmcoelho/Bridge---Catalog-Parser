"""Semantic rules for dependencies.yml: within one file (E/W codes) and across files (X codes).

Codes
  E001 unreadable / invalid YAML        E002 schema violation (type, enum, unknown field, ...)
  E101 duplicate component name         E102 local_component not declared in this file
  E103 inline traits on an entry that has `component` (traits live on the component)
  E104 external upstream missing inline traits (category, technology, criticality, description)
  E105 inline traits on a downstream entry without `component`
  E106 entry with `component` but no `local_component`
  E107 downstream entry without `local_component`
  E108 dependency on itself             E109 duplicate entry in the same list
  E110 git.path does not end with `ci`  E112 `via` points at itself
  W201 port without protocol            W202 data component with protocol/port
  X001 same ci in two files             X002 component not declared by the referenced ci
  X003 link without the mirror entry on the other side (blame = the CI that must add it)
  W203 CI referenced with a component but its catalog was not loaded: link not checked
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .issues import ERROR, WARNING, Issue
from .models import Category, Dependency, DependencyCatalog
from .parser import Parsed, parse_dependencies

INLINE_TRAITS = ("category", "technology", "protocol", "port", "criticality", "description")
EXTERNAL_REQUIRED = ("category", "technology", "criticality", "description")
SIDES = ("upstream", "downstream")

Finding = tuple[str, str, tuple, str]  # code, severity, location, message


def _entries(cat: DependencyCatalog) -> Iterator[tuple[str, int, Dependency]]:
    for side in SIDES:
        for i, dep in enumerate(getattr(cat.dependencies, side)):
            yield side, i, dep


def _set_traits(dep: Dependency) -> list[str]:
    return [t for t in INLINE_TRAITS if getattr(dep, t) is not None]


def rule_components(cat: DependencyCatalog) -> Iterator[Finding]:
    seen: set[str] = set()
    for i, c in enumerate(cat.components):
        if c.name in seen:
            yield "E101", ERROR, ("components", i, "name"), f"duplicate component '{c.name}'"
        seen.add(c.name)
        if c.port is not None and c.protocol is None:
            yield "W201", WARNING, ("components", i, "port"), f"component '{c.name}' has a port but no protocol"
        if c.category == Category.DATA and (c.protocol or c.port):
            yield "W202", WARNING, ("components", i), f"data component '{c.name}' should not have protocol/port"


def rule_entries(cat: DependencyCatalog) -> Iterator[Finding]:
    local = {c.name for c in cat.components}
    seen: set[tuple] = set()
    for side, i, dep in _entries(cat):
        at = ("dependencies", side, i)
        if dep.ci == cat.ci:
            yield "E108", ERROR, at + ("ci",), "a CI cannot depend on itself"
        if dep.via == cat.ci:
            yield "E112", ERROR, at + ("via",), "`via` points at this same CI"
        if dep.local_component is not None and dep.local_component not in local:
            yield "E102", ERROR, at + ("local_component",), \
                f"local_component '{dep.local_component}' is not declared in components"
        key = (side, dep.ci, dep.component, dep.local_component)
        if key in seen:
            yield "E109", ERROR, at, f"duplicate entry for {dep.ci}/{dep.component} (local {dep.local_component})"
        seen.add(key)

        traits = _set_traits(dep)
        if dep.component is not None:
            if traits:
                yield "E103", ERROR, at, f"traits {traits} belong on {dep.ci}'s component '{dep.component}', not here"
            if dep.local_component is None:
                yield "E106", ERROR, at, "entry with `component` needs `local_component`"
        elif side == "downstream":
            if traits:
                yield "E105", ERROR, at, f"downstream entry without `component` cannot carry traits {traits}"
        else:
            missing = [t for t in EXTERNAL_REQUIRED if getattr(dep, t) is None]
            if missing:
                yield "E104", ERROR, at, f"external system '{dep.ci}' is missing {missing}"
        if side == "downstream" and dep.local_component is None:
            yield "E107", ERROR, at, "downstream entry needs `local_component`"


def rule_identity(cat: DependencyCatalog) -> Iterator[Finding]:
    if cat.git.path.rstrip("/").rsplit("/", 1)[-1] != cat.ci:
        yield "E110", ERROR, ("git", "path"), f"git.path should end with the ci name '{cat.ci}'"


FILE_RULES = (rule_identity, rule_components, rule_entries)


def lint_file(path: Path) -> Parsed:
    """Parse + single-file rules. Rules only run when the schema is valid."""
    parsed = parse_dependencies(path)
    if parsed.catalog is not None:
        for rule in FILE_RULES:
            for code, severity, loc, msg in rule(parsed.catalog):
                parsed.issues.append(parsed.issue(code, severity, msg, loc))
    return parsed


def lint_cross(files: list[Parsed]) -> list[Issue]:
    """Rules that need several catalogs at once. CIs absent from `files` are treated as external."""
    issues: list[Issue] = []
    by_ci: dict[str, Parsed] = {}
    for p in files:
        if p.catalog is None:
            continue
        if p.catalog.ci in by_ci:
            issues.append(p.issue("X001", ERROR, f"ci '{p.catalog.ci}' also declared in {by_ci[p.catalog.ci].path}", ("ci",)))
        else:
            by_ci[p.catalog.ci] = p

    for p in by_ci.values():
        cat = p.catalog
        for side, i, dep in _entries(cat):
            other = by_ci.get(dep.ci)
            if dep.component is None:
                continue
            at = ("dependencies", side, i)
            if other is None:
                issues.append(p.issue("W203", WARNING, f"catalog of '{dep.ci}' was not loaded: "
                                      f"link to {dep.ci}/{dep.component} not checked", at + ("ci",)))
                continue
            if dep.component not in {c.name for c in other.catalog.components}:
                issues.append(p.issue("X002", ERROR, f"component '{dep.component}' is not declared by {dep.ci}", at + ("component",)))
                continue
            if dep.local_component is None:
                continue  # already E106/E107
            opposite = "downstream" if side == "upstream" else "upstream"
            mirrored = any(o.ci == cat.ci and o.component == dep.local_component and o.local_component == dep.component
                           for o in getattr(other.catalog.dependencies, opposite))
            if not mirrored:
                issues.append(p.issue(
                    "X003", ERROR,
                    f"{dep.ci}.{opposite} has no entry (ci: {cat.ci}, component: {dep.local_component}, "
                    f"local_component: {dep.component})", at, blame=dep.ci))
    return issues
