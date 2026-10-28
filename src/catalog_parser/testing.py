"""pytest helper: `assert_catalog_valid()` in a repository's own test suite."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .api import check_repo
from .issues import ERROR


def assert_catalog_valid(root: str | Path = ".", peers: Iterable[str | Path] | None = None, strict: bool = False) -> None:
    """Fail with every finding listed. `strict` also fails on warnings (including W203)."""
    failing = [i for i in check_repo(root, peers) if strict or i.severity == ERROR]
    assert not failing, "invalid catalog:\n" + "\n".join(i.format() for i in failing)
