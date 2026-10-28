"""Lint findings: what the linter reports, independent of how it is printed."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


ERROR = Severity.ERROR
WARNING = Severity.WARNING


@dataclass(frozen=True)
class RuleInfo:
    """What a finding code means: shown by `catalog-lint --list-rules`."""

    code: str          # E### single-file error, W### warning, X### cross-file error
    severity: Severity
    summary: str


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str
    path: Path
    line: int | None = None
    location: str = ""  # dotted path inside the file, e.g. dependencies.upstream[3].component
    blame: str = ""     # CI that has to change when that is not the file reporting it (X003)

    def format(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else f"{self.path}"
        loc = f" [{self.location}]" if self.location else ""
        return f"{where}: {self.severity} {self.code}{loc} {self.message}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        d["severity"] = str(self.severity)
        return d


def sort_issues(issues: Iterable[Issue]) -> list[Issue]:
    return sorted(issues, key=lambda i: (str(i.path), i.line or 0, i.code))


def format_location(loc: tuple) -> str:
    """('dependencies', 'upstream', 3, 'ci') -> 'dependencies.upstream[3].ci'."""
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out
