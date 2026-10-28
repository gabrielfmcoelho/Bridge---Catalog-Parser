"""Finding catalog files under the paths a user gives."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .config import Layout


class CatalogDiscoverer:
    def __init__(self, layout: Layout, filenames: Iterable[str]):
        self.layout = layout
        self.filenames = tuple(filenames)

    def discover(self, paths: Iterable[str | Path], filenames: Iterable[str] | None = None) -> list[Path]:
        """Files given explicitly are kept as-is; directories are searched for <catalog_dir>/<filename>,
        skipping `layout.skip_dirs` below the searched directory."""
        names = self.filenames if filenames is None else tuple(filenames)
        found: list[Path] = []
        for p in map(Path, paths):
            if p.is_file():
                found.append(p)
                continue
            for name in names:
                for f in sorted(p.rglob(f"{self.layout.catalog_dir}/{name}")):
                    if not self.layout.skip_dirs & set(f.relative_to(p).parts[:-1]):
                        found.append(f)
        return list(dict.fromkeys(found))
