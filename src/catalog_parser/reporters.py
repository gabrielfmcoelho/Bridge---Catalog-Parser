"""Output formats of `catalog-lint`. A new format is one Reporter subclass added to REPORTERS."""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TextIO

from .issues import ERROR, Issue


class Reporter(ABC):
    @abstractmethod
    def report(self, issues: Sequence[Issue], out: TextIO, err: TextIO) -> None: ...

    def emit(self, issues: Sequence[Issue]) -> None:
        self.report(issues, sys.stdout, sys.stderr)


class TextReporter(Reporter):
    """One `path:line: severity CODE [location] message` per finding; a summary on stderr."""

    def report(self, issues: Sequence[Issue], out: TextIO, err: TextIO) -> None:
        for i in issues:
            print(i.format(), file=out)
        errors = sum(i.severity == ERROR for i in issues)
        print(f"{errors} error(s), {len(issues) - errors} warning(s)", file=err)


class JsonReporter(Reporter):
    """A JSON array of findings, for other tools."""

    def report(self, issues: Sequence[Issue], out: TextIO, err: TextIO) -> None:
        print(json.dumps([i.to_dict() for i in issues], indent=2, ensure_ascii=False), file=out)


REPORTERS: dict[str, type[Reporter]] = {"text": TextReporter, "json": JsonReporter}
