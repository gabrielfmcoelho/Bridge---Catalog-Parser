"""Lint findings: what the linter reports, independent of how it is printed."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    code: str          # E### single-file error, W### warning, X### cross-file error
    severity: str      # ERROR | WARNING
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
        return d


def format_location(loc: tuple) -> str:
    """('dependencies', 'upstream', 3, 'ci') -> 'dependencies.upstream[3].ci'."""
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out
