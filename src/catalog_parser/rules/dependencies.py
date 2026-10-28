"""Rules of the dependencies catalog: within one file (E1xx, W2xx) and across files (X0xx, W203)."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterator, Sequence

from ..config import Vocabulary
from ..issues import ERROR, WARNING, RuleInfo
from ..models import Component, Dependency, DependencyCatalog
from ..parser import Parsed
from .base import CrossRule, FileRule, Finding

INLINE_TRAITS = ("category", "technology", "protocol", "port", "criticality", "description")
EXTERNAL_REQUIRED = ("category", "technology", "criticality", "description")
SIDES = ("upstream", "downstream")


def entries(cat: DependencyCatalog) -> Iterator[tuple[str, int, Dependency]]:
    for side in SIDES:
        for i, dep in enumerate(getattr(cat.dependencies, side)):
            yield side, i, dep


def set_traits(dep: Dependency) -> list[str]:
    return [t for t in INLINE_TRAITS if getattr(dep, t) is not None]


def opposite(side: str) -> str:
    return "downstream" if side == "upstream" else "upstream"


# --- identity --------------------------------------------------------------------------------

class GitPathMatchesCi(FileRule):
    info = RuleInfo("E110", ERROR, "`git.path` does not end with the `ci` name")

    def check(self, catalog: DependencyCatalog, vocabulary: Vocabulary) -> Iterator[Finding]:
        if catalog.git.path.rstrip("/").rsplit("/", 1)[-1] != catalog.ci:
            yield Finding(("git", "path"), f"git.path should end with the ci name '{catalog.ci}'")


# --- components ------------------------------------------------------------------------------

class ComponentRule(FileRule):
    """Checks each component on its own."""

    def check(self, catalog: DependencyCatalog, vocabulary: Vocabulary) -> Iterator[Finding]:
        for i, c in enumerate(catalog.components):
            yield from self.check_component(c, ("components", i), vocabulary)

    @abstractmethod
    def check_component(self, c: Component, at: tuple, vocabulary: Vocabulary) -> Iterator[Finding]: ...


class DuplicateComponent(FileRule):
    info = RuleInfo("E101", ERROR, "duplicate component name")

    def check(self, catalog: DependencyCatalog, vocabulary: Vocabulary) -> Iterator[Finding]:
        seen: set[str] = set()
        for i, c in enumerate(catalog.components):
            if c.name in seen:
                yield Finding(("components", i, "name"), f"duplicate component '{c.name}'")
            seen.add(c.name)


class PortWithoutProtocol(ComponentRule):
    info = RuleInfo("W201", WARNING, "component with `port` but no `protocol`")

    def check_component(self, c: Component, at: tuple, vocabulary: Vocabulary) -> Iterator[Finding]:
        if c.port is not None and c.protocol is None:
            yield Finding(at + ("port",), f"component '{c.name}' has a port but no protocol")


class DataComponentWithEndpoint(ComponentRule):
    info = RuleInfo("W202", WARNING, "data component (vocabulary.data_categories) with `protocol`/`port`")

    def check_component(self, c: Component, at: tuple, vocabulary: Vocabulary) -> Iterator[Finding]:
        if vocabulary.is_data(c.category) and (c.protocol or c.port):
            yield Finding(at, f"data component '{c.name}' should not have protocol/port")


# --- dependency entries ----------------------------------------------------------------------

class EntryRule(FileRule):
    """Checks each upstream/downstream entry on its own; `at` is the entry's location."""

    def check(self, catalog: DependencyCatalog, vocabulary: Vocabulary) -> Iterator[Finding]:
        for side, i, dep in entries(catalog):
            yield from self.check_entry(catalog, side, dep, ("dependencies", side, i))

    @abstractmethod
    def check_entry(self, catalog: DependencyCatalog, side: str, dep: Dependency, at: tuple) -> Iterator[Finding]: ...


class SelfDependency(EntryRule):
    info = RuleInfo("E108", ERROR, "CI depending on itself")

    def check_entry(self, catalog, side, dep, at):
        if dep.ci == catalog.ci:
            yield Finding(at + ("ci",), "a CI cannot depend on itself")


class SelfVia(EntryRule):
    info = RuleInfo("E112", ERROR, "`via` points at this same CI")

    def check_entry(self, catalog, side, dep, at):
        if dep.via == catalog.ci:
            yield Finding(at + ("via",), "`via` points at this same CI")


class UnknownLocalComponent(EntryRule):
    info = RuleInfo("E102", ERROR, "`local_component` not declared in this file")

    def check_entry(self, catalog, side, dep, at):
        if dep.local_component is not None and dep.local_component not in {c.name for c in catalog.components}:
            yield Finding(at + ("local_component",),
                          f"local_component '{dep.local_component}' is not declared in components")


class DuplicateEntry(FileRule):
    info = RuleInfo("E109", ERROR, "duplicate entry in the same list")

    def check(self, catalog: DependencyCatalog, vocabulary: Vocabulary) -> Iterator[Finding]:
        seen: set[tuple] = set()
        for side, i, dep in entries(catalog):
            key = (side, dep.ci, dep.component, dep.local_component)
            if key in seen:
                yield Finding(("dependencies", side, i),
                              f"duplicate entry for {dep.ci}/{dep.component} (local {dep.local_component})")
            seen.add(key)


class TraitsOnLinkedEntry(EntryRule):
    info = RuleInfo("E103", ERROR, "inline traits on an entry with `component` (traits live on the component)")

    def check_entry(self, catalog, side, dep, at):
        traits = set_traits(dep)
        if dep.component is not None and traits:
            yield Finding(at, f"traits {traits} belong on {dep.ci}'s component '{dep.component}', not here")


class LinkedEntryWithoutLocalComponent(EntryRule):
    info = RuleInfo("E106", ERROR, "entry with `component` but no `local_component`")

    def check_entry(self, catalog, side, dep, at):
        if dep.component is not None and dep.local_component is None:
            yield Finding(at, "entry with `component` needs `local_component`")


class TraitsOnPlainDownstream(EntryRule):
    info = RuleInfo("E105", ERROR, "`downstream` entry without `component` carrying traits")

    def check_entry(self, catalog, side, dep, at):
        traits = set_traits(dep)
        if dep.component is None and side == "downstream" and traits:
            yield Finding(at, f"downstream entry without `component` cannot carry traits {traits}")


class ExternalMissingTraits(EntryRule):
    info = RuleInfo("E104", ERROR, "external `upstream` without `category`/`technology`/`criticality`/`description`")

    def check_entry(self, catalog, side, dep, at):
        if dep.component is None and side == "upstream":
            missing = [t for t in EXTERNAL_REQUIRED if getattr(dep, t) is None]
            if missing:
                yield Finding(at, f"external system '{dep.ci}' is missing {missing}")


class DownstreamWithoutLocalComponent(EntryRule):
    info = RuleInfo("E107", ERROR, "`downstream` entry without `local_component`")

    def check_entry(self, catalog, side, dep, at):
        if side == "downstream" and dep.local_component is None:
            yield Finding(at, "downstream entry needs `local_component`")


# --- across files ----------------------------------------------------------------------------

def index_by_ci(files: Sequence[Parsed]) -> dict[str, Parsed]:
    """Loaded catalogs by CI; the first file wins when a CI is declared twice (X001)."""
    by_ci: dict[str, Parsed] = {}
    for p in files:
        if p.catalog is not None:
            by_ci.setdefault(p.catalog.ci, p)
    return by_ci


class DuplicateCi(CrossRule):
    info = RuleInfo("X001", ERROR, "same `ci` declared in two files")

    def check(self, files: Sequence[Parsed], vocabulary: Vocabulary) -> Iterator[tuple[Parsed, Finding]]:
        first = index_by_ci(files)
        for p in files:
            if p.catalog is not None and first[p.catalog.ci] is not p:
                yield p, Finding(("ci",), f"ci '{p.catalog.ci}' also declared in {first[p.catalog.ci].path}")


class LinkRule(CrossRule):
    """Checks every entry that names a component of another CI against that CI's catalog
    (`other`, None when it was not loaded). CIs absent from the files are treated as external."""

    def check(self, files: Sequence[Parsed], vocabulary: Vocabulary) -> Iterator[tuple[Parsed, Finding]]:
        by_ci = index_by_ci(files)
        for p in by_ci.values():
            for side, i, dep in entries(p.catalog):
                if dep.component is not None:
                    other = by_ci.get(dep.ci)
                    for finding in self.check_link(p.catalog, side, dep, ("dependencies", side, i),
                                                   other.catalog if other else None):
                        yield p, finding

    @abstractmethod
    def check_link(self, catalog: DependencyCatalog, side: str, dep: Dependency, at: tuple,
                   other: DependencyCatalog | None) -> Iterator[Finding]: ...


class UncheckedLink(LinkRule):
    info = RuleInfo("W203", WARNING, "CI referenced with `component` but its catalog was not loaded: link not checked")

    def check_link(self, catalog, side, dep, at, other):
        if other is None:
            yield Finding(at + ("ci",), f"catalog of '{dep.ci}' was not loaded: link to {dep.ci}/{dep.component} not checked")


class UnknownRemoteComponent(LinkRule):
    info = RuleInfo("X002", ERROR, "`component` not declared by the referenced CI")

    def check_link(self, catalog, side, dep, at, other):
        if other is not None and dep.component not in {c.name for c in other.components}:
            yield Finding(at + ("component",), f"component '{dep.component}' is not declared by {dep.ci}")


class MissingMirror(LinkRule):
    info = RuleInfo("X003", ERROR, "link without the mirror entry on the other side; `blame` = the CI that must add it")

    def check_link(self, catalog, side, dep, at, other):
        if other is None or dep.local_component is None:  # W203 / E106-E107 already say so
            return
        if dep.component not in {c.name for c in other.components}:  # X002 already says so
            return
        back = opposite(side)
        mirrored = any(o.ci == catalog.ci and o.component == dep.local_component and o.local_component == dep.component
                       for o in getattr(other.dependencies, back))
        if not mirrored:
            yield Finding(at, f"{dep.ci}.{back} has no entry (ci: {catalog.ci}, component: {dep.local_component}, "
                              f"local_component: {dep.component})", blame=dep.ci)


FILE_RULES: tuple[FileRule, ...] = (
    GitPathMatchesCi(),
    DuplicateComponent(), PortWithoutProtocol(), DataComponentWithEndpoint(),
    SelfDependency(), SelfVia(), UnknownLocalComponent(), DuplicateEntry(),
    TraitsOnLinkedEntry(), LinkedEntryWithoutLocalComponent(), TraitsOnPlainDownstream(),
    ExternalMissingTraits(), DownstreamWithoutLocalComponent(),
)

CROSS_RULES: tuple[CrossRule, ...] = (DuplicateCi(), UncheckedLink(), UnknownRemoteComponent(), MissingMirror())
