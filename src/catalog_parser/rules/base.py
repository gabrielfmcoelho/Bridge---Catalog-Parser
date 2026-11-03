"""Rule abstractions. A rule owns exactly one finding code; the Linter decides which rules run
(RuleSelection) and turns their findings into Issues with file and line."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel

from ..config import Vocabulary
from ..issues import RuleInfo
from ..parser import Parsed


@dataclass(frozen=True)
class Finding:
    location: tuple  # path inside the file, e.g. ("dependencies", "upstream", 3, "ci")
    message: str
    blame: str = ""  # CI that has to change, when it is not the file reporting it


class Rule(ABC):
    info: ClassVar[RuleInfo]

    @property
    def code(self) -> str:
        return self.info.code


class FileRule(Rule):
    """Looks at one catalog that already passed schema validation."""

    @abstractmethod
    def check(self, catalog: BaseModel, vocabulary: Vocabulary) -> Iterator[Finding]: ...


class CrossRule(Rule):
    """Looks at every loaded catalog of one kind at once; findings say which file they belong to."""

    @abstractmethod
    def check(self, files: Sequence[Parsed], vocabulary: Vocabulary) -> Iterator[tuple[Parsed, Finding]]: ...
