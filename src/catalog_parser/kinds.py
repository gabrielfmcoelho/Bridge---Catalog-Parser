"""Registry of catalog kinds: file name inside the catalog folder -> model and rules.

A new catalog file (e.g. `catalog/owners.yml`) is supported by writing its model and rules and
registering one CatalogKind; discovery, CLI and output formats need no change:

    registry = default_registry()
    registry.register(CatalogKind("owners.yml", OwnersCatalog, file_rules=(MyRule(),)))
    Linter(settings, registry).lint_paths([Path(".")])
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from pydantic import BaseModel

from .config import Vocabulary
from .models import DependencyCatalog
from .parser import CatalogParser
from .rules.base import CrossRule, FileRule, Rule
from .rules.dependencies import CROSS_RULES, FILE_RULES


@dataclass(frozen=True)
class CatalogKind:
    filename: str
    model: type[BaseModel]
    file_rules: tuple[FileRule, ...] = ()
    cross_rules: tuple[CrossRule, ...] = ()

    def parser(self, vocabulary: Vocabulary) -> CatalogParser:
        return CatalogParser(self.model, vocabulary)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return (*self.file_rules, *self.cross_rules)


DEPENDENCIES = CatalogKind("dependencies.yml", DependencyCatalog, FILE_RULES, CROSS_RULES)


class KindRegistry:
    def __init__(self, kinds: Iterable[CatalogKind] = ()):
        self._kinds: dict[str, CatalogKind] = {}
        for kind in kinds:
            self.register(kind)

    def register(self, kind: CatalogKind) -> None:
        if kind.filename in self._kinds:
            raise ValueError(f"catalog kind '{kind.filename}' is already registered")
        self._kinds[kind.filename] = kind

    def get(self, filename: str) -> CatalogKind | None:
        return self._kinds.get(filename)

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(self._kinds)

    def rules(self) -> list[Rule]:
        return [rule for kind in self for rule in kind.rules]

    def __iter__(self) -> Iterator[CatalogKind]:
        return iter(self._kinds.values())


def default_registry() -> KindRegistry:
    return KindRegistry([DEPENDENCIES])
