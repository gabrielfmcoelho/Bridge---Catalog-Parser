"""Entry point for a repository that depends on this library: lint ITS catalog, optionally with
the catalogs of other repositories as context for the cross-file rules."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .issues import Issue
from .kinds import discover
from .lint import lint_cross, lint_file

PEERS_ENV = "CATALOG_PEERS"  # os.pathsep-separated files/folders, used when `peers` is not given


def check_repo(root: str | Path = ".", peers: Iterable[str | Path] | None = None, cross: bool = True) -> list[Issue]:
    """Findings that concern the repository at `root` (or the dependencies.yml file itself).

    Only this repo's own file is linted in full. Peers are read as context: their own problems are
    not reported, but a peer that points at this CI without a mirror here IS (X003, blame = this CI).
    Without peers the cross-file rules cannot see the other side, and W203 says so.
    """
    root = Path(root)
    file = root if root.is_file() else root / "catalog" / "dependencies.yml"
    if peers is None:
        peers = [Path(p) for p in os.environ.get(PEERS_ENV, "").split(os.pathsep) if p]
    own = lint_file(file)
    issues = list(own.issues)
    if cross:
        others = [lint_file(f) for f in discover([Path(p) for p in peers]) if f.resolve() != file.resolve()]
        mine = own.catalog.ci if own.catalog else None
        issues += [i for i in lint_cross([own, *others]) if i.path == file or (mine and i.blame == mine)]
    return sorted(issues, key=lambda i: (str(i.path), i.line or 0, i.code))
