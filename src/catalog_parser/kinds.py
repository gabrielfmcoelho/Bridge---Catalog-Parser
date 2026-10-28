"""Registry of catalog kinds: file name inside a `catalog/` folder -> how to lint it.

A new catalog file (e.g. `catalog/owners.yml`) is supported by writing its models + rules and
adding one entry here; discovery, CLI and output formats need no change."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .lint import lint_cross, lint_file
from .parser import Parsed

# kind file name -> single-file linter
FILE_LINTERS: dict[str, Callable[[Path], Parsed]] = {
    "dependencies.yml": lint_file,
}

# kind file name -> cross-file linter (receives every Parsed of that kind)
CROSS_LINTERS: dict[str, Callable[[list[Parsed]], list]] = {
    "dependencies.yml": lint_cross,
}

SKIP_DIRS = {".git", ".venv", "node_modules", "dbt_packages", "target", "__pycache__"}


def discover(paths: list[Path]) -> list[Path]:
    """Files given explicitly are kept as-is; directories are searched for catalog/<known kind>."""
    found: list[Path] = []
    for p in paths:
        if p.is_file():
            found.append(p)
            continue
        for kind in FILE_LINTERS:
            for f in sorted(p.rglob(f"catalog/{kind}")):
                if not SKIP_DIRS & set(f.parts):
                    found.append(f)
    return list(dict.fromkeys(found))
