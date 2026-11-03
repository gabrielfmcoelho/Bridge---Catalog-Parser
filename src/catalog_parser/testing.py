"""pytest helper: `assert_catalog_valid()` in a repository's own test suite."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .config import Settings
from .issues import ERROR
from .repository import check_repo


def assert_catalog_valid(root: str | Path = ".", peers: Iterable[str | Path] | None = None, strict: bool = False,
                         settings: Settings | None = None) -> None:
    """Fail with every finding listed. `strict` also fails on warnings (including W203).
    Settings default to the config file found from `root`."""
    failing = [i for i in check_repo(root, peers, settings=settings) if strict or i.severity == ERROR]
    assert not failing, "invalid catalog:\n" + "\n".join(i.format() for i in failing)
