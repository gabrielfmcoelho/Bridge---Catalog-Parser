"""Entry point for a repository that depends on this library: lint ITS catalog, optionally with
the catalogs of other repositories (peers, local or remote) as context for the cross-file rules."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

from .config import Layout, Settings
from .issues import Issue, sort_issues
from .kinds import DEPENDENCIES, CatalogKind
from .linter import Linter
from .parser import Parsed
from .remote import RemoteConfigLoader, is_url

_ENV_SPLIT = re.compile(rf"(?:{re.escape(os.pathsep)}(?!//)|[,;])")


def _split_peers_env(raw: str) -> list[str]:
    return [p.strip() for p in _ENV_SPLIT.split(raw) if p.strip()]


class Repository:
    """A repository folder, or one catalog file inside it."""

    def __init__(self, path: str | Path, layout: Layout | None = None):
        self.path = Path(path)
        self.layout = layout or Layout()

    def catalog_file(self, filename: str = DEPENDENCIES.filename) -> Path:
        return self.path if self.path.is_file() else self.path / self.layout.catalog_dir / filename

    @property
    def root(self) -> Path:
        if not self.path.is_file():
            return self.path
        parents = self.path.parents
        return parents[self.layout.depth] if self.layout.depth < len(parents) else self.path.parent


class PeerLoader:
    """Parses the catalogs of other repositories, given explicitly, via `layout.peers_env`, or `layout.peers`."""

    def __init__(self, linter: Linter, remote_loader: RemoteConfigLoader | None = None):
        self.linter = linter
        self.remote_loader = remote_loader

    def locations(self, peers: Iterable[str | Path] | None) -> list[str | Path]:
        if peers is None:
            env_val = os.environ.get(self.linter.settings.layout.peers_env, "")
            if env_val:
                return _split_peers_env(env_val)
            return list(self.linter.settings.layout.peers)
        return [p if is_url(p) else Path(p) for p in peers]

    def paths(self, peers: Iterable[str | Path] | None) -> list[Path]:
        return [Path(p) for p in self.locations(peers) if not is_url(p)]

    def load(
        self,
        peers: Iterable[str | Path] | None,
        exclude: Path,
        kind: CatalogKind = DEPENDENCIES,
    ) -> list[Parsed]:
        locs = self.locations(peers)
        local_paths = [Path(p) for p in locs if not is_url(p)]
        remote_urls = [str(p) for p in locs if is_url(p)]

        files = self.linter.discoverer.discover(local_paths, filenames=[kind.filename])
        loaded = [self.linter.lint_file(f, kind) for f in files if f.resolve() != exclude.resolve()]
        for url in remote_urls:
            loaded.append(self.linter.lint_url(url, kind, loader=self.remote_loader))
        return loaded


class RepositoryChecker:
    """Findings that concern one repository.

    Only the repository's own file is linted in full. Peers are read as context: their own problems
    are not reported, but a peer that points at this CI without a mirror here IS (X003, blame = this CI).
    Without peers the cross-file rules cannot see the other side, and W203 says so.
    """

    def __init__(self, linter: Linter, kind: CatalogKind = DEPENDENCIES, peer_loader: PeerLoader | None = None):
        self.linter = linter
        self.kind = kind
        self.peer_loader = peer_loader or PeerLoader(linter)

    def check(
        self,
        root: str | Path = ".",
        peers: Iterable[str | Path] | None = None,
        cross: bool = True,
    ) -> list[Issue]:
        file = Repository(root, self.linter.settings.layout).catalog_file(self.kind.filename)
        own = self.linter.lint_file(file, self.kind)
        issues = list(own.issues)
        if cross:
            others = self.peer_loader.load(peers, file, self.kind)
            mine = getattr(own.catalog, "ci", None)
            issues += [
                i for i in self.linter.lint_cross([own, *others], self.kind)
                if i.path == file or (mine and i.blame == mine)
            ]
        return sort_issues(issues)


def check_repo(
    root: str | Path = ".",
    peers: Iterable[str | Path] | None = None,
    cross: bool = True,
    settings: Settings | None = None,
) -> list[Issue]:
    """Findings that concern the repository at `root` (or the catalog file itself).
    Settings default to the config file found from `root` (see Settings.discover)."""
    return RepositoryChecker(Linter(settings or Settings.discover(root))).check(root, peers, cross)
