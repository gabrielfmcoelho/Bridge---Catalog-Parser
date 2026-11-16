"""Config and catalog files read over HTTPS from a remote configuration repository.

Supported URL formats (`location`):

- **GitLab file page** (`https://host/group/project/-/blob/<ref>/<path>` or `/-/raw/`): translated
  into the GitLab Repository Files API (`/api/v4/projects/<project>/repository/files/<path>/raw?ref=<ref>`)
  and authenticated with `PRIVATE-TOKEN` (requires `read_api` scope);
- **GitLab API URL** (`.../api/v4/...`): fetched as-is, with `PRIVATE-TOKEN`;
- **GitHub file page** (`https://github.com/<owner>/<repo>/blob/<ref>/<path>` or `/raw/`): translated
  into `https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>` and authenticated with
  `Authorization: Bearer <token>`;
- **GitHub Contents API URL** (`https://api.github.com/repos/<owner>/<repo>/contents/<path>`):
  fetched with `Accept: application/vnd.github.raw+json` and `Authorization: Bearer <token>`;
- **Bitbucket file page** (`https://bitbucket.org/<workspace>/<repo>/src/<ref>/<path>`): translated
  into the Bitbucket 2.0 source API (`/2.0/repositories/<workspace>/<repo>/src/<ref>/<path>`) with
  `Authorization: Bearer <token>`;
- **Any other HTTPS URL** (e.g. `raw.githubusercontent.com`, Gitea, Forgejo, S3): fetched as-is,
  with `Authorization: Bearer <token>` (or a custom header from `$CATALOG_PARSER_AUTH_HEADER`).

The token comes from `$CATALOG_PARSER_TOKEN`, never from the command line (shell history), and is
never sent over plain `http://`. The network call is the injectable `fetch`, so the loader is
tested without a network. Optional local caching is enabled by setting `$CATALOG_PARSER_CACHE_TTL`
(in seconds).
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

TOKEN_ENV = "CATALOG_PARSER_TOKEN"
AUTH_HEADER_ENV = "CATALOG_PARSER_AUTH_HEADER"
CACHE_TTL_ENV = "CATALOG_PARSER_CACHE_TTL"
CACHE_DIR_ENV = "CATALOG_PARSER_CACHE_DIR"
REQUEST_TIMEOUT = 30

_GITLAB_PAGE = re.compile(
    r"^(?P<base>https?://[^/]+)/(?P<project>[^?#]+?)/-/(?:blob|raw)/(?P<ref>[^/]+)/(?P<path>[^?#]+)"
)
_GITLAB_API_FILE = re.compile(
    r"^(?P<prefix>https?://[^/]+/api/v4/projects/[^/]+/repository/files/)(?P<path>[^/?#]+)(?P<suffix>/raw(?:\?.*)?)$"
)
_GITHUB_PAGE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:blob|raw)/(?P<ref>[^/]+)/(?P<path>[^?#]+)"
)
_GITHUB_API_FILE = re.compile(
    r"^https?://api\.github\.com/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/contents/(?P<path>[^?#]+)"
)
_BITBUCKET_PAGE = re.compile(
    r"^https?://bitbucket\.org/(?P<workspace>[^/]+)/(?P<repo>[^/]+)/(?:src|raw)/(?P<ref>[^/]+)/(?P<path>[^?#]+)"
)


class RemoteError(Exception):
    """A remote resource could not be read; the message never contains the token."""


class FetchError(Exception):
    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.status = status


Fetcher = Callable[[str, Mapping[str, str], float], bytes]


def urllib_fetch(url: str, headers: Mapping[str, str], timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} {e.reason}", e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FetchError(str(getattr(e, "reason", e))) from None


def is_url(location: object) -> bool:
    return str(location).startswith(("https://", "http://"))


@dataclass(frozen=True)
class RemoteFile:
    location: str  # what the user gave
    url: str       # what is fetched
    name: str      # file name, to tell a pyproject.toml apart
    gitlab: bool = False
    provider: str = "generic"
    extra_headers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, location: str) -> RemoteFile:
        for provider in PROVIDERS:
            parsed = provider.parse(location)
            if parsed is not None:
                return parsed
        return GenericHttpsProvider(). resolve(location)

    def headers(self, token: str | None, auth_header: str | None = None) -> dict[str, str]:
        hdrs = dict(self.extra_headers)
        if not token:
            return hdrs
        if auth_header:
            hdrs[auth_header] = token
        elif self.gitlab:
            hdrs["PRIVATE-TOKEN"] = token
        else:
            hdrs["Authorization"] = f"Bearer {token}"
        return hdrs

    def resolve_relative(self, relative_path: str) -> str:
        """Resolve a relative path (e.g. `./base.toml` or `../peers/svc.yml`) against `self.location`."""
        if is_url(relative_path):
            return relative_path
        api = _GITLAB_API_FILE.match(self.location)
        if api:
            current_dir = posixpath.dirname(unquote(api["path"]))
            joined = posixpath.normpath(posixpath.join(current_dir, relative_path)).lstrip("/")
            return f"{api['prefix']}{quote(joined, safe='')}{api['suffix']}"
        parsed = urlparse(self.location)
        base_dir = posixpath.dirname(parsed.path)
        norm_path = posixpath.normpath(posixpath.join(base_dir, relative_path))
        if not norm_path.startswith("/"):
            norm_path = "/" + norm_path
        return urlunparse((parsed.scheme, parsed.netloc, norm_path, parsed.params, parsed.query, ""))


class RemoteProvider(ABC):
    """Translates a user-facing repository URL into a raw file fetch descriptor."""

    @abstractmethod
    def parse(self, location: str) -> RemoteFile | None: ...


class GitLabProvider(RemoteProvider):
    def parse(self, location: str) -> RemoteFile | None:
        page = _GITLAB_PAGE.match(location)
        if page:
            project, path = page["project"].strip("/"), unquote(page["path"])
            url = (
                f"{page['base']}/api/v4/projects/{quote(project, safe='')}/repository/files/"
                f"{quote(path, safe='')}/raw?ref={quote(page['ref'], safe='')}"
            )
            return RemoteFile(location, url, path.rsplit("/", 1)[-1], gitlab=True, provider="gitlab")
        api = _GITLAB_API_FILE.match(location)
        if api:
            name = unquote(api["path"]).rsplit("/", 1)[-1]
            return RemoteFile(location, location, name, gitlab=True, provider="gitlab")
        if "/api/v4/" in location:
            return RemoteFile(location, location, "", gitlab=True, provider="gitlab")
        return None


class GitHubProvider(RemoteProvider):
    def parse(self, location: str) -> RemoteFile | None:
        page = _GITHUB_PAGE.match(location)
        if page:
            path = unquote(page["path"])
            url = f"https://raw.githubusercontent.com/{page['owner']}/{page['repo']}/{page['ref']}/{path}"
            return RemoteFile(location, url, path.rsplit("/", 1)[-1], gitlab=False, provider="github")
        api = _GITHUB_API_FILE.match(location)
        if api:
            path = unquote(api["path"])
            return RemoteFile(
                location,
                location,
                path.rsplit("/", 1)[-1],
                gitlab=False,
                provider="github",
                extra_headers={"Accept": "application/vnd.github.raw+json"},
            )
        if "raw.githubusercontent.com/" in location:
            name = urlparse(location).path.rsplit("/", 1)[-1]
            return RemoteFile(location, location, name, gitlab=False, provider="github")
        return None


class BitbucketProvider(RemoteProvider):
    def parse(self, location: str) -> RemoteFile | None:
        page = _BITBUCKET_PAGE.match(location)
        if page:
            path = unquote(page["path"])
            url = (
                f"https://api.bitbucket.org/2.0/repositories/{page['workspace']}/{page['repo']}"
                f"/src/{page['ref']}/{path}"
            )
            return RemoteFile(location, url, path.rsplit("/", 1)[-1], gitlab=False, provider="bitbucket")
        return None


class GenericHttpsProvider(RemoteProvider):
    def parse(self, location: str) -> RemoteFile | None:
        return self.resolve(location) if is_url(location) else None

    def resolve(self, location: str) -> RemoteFile:
        name = urlparse(location).path.rsplit("/", 1)[-1]
        return RemoteFile(location, location, name, gitlab=False, provider="generic")


PROVIDERS: list[RemoteProvider] = [
    GitLabProvider(),
    GitHubProvider(),
    BitbucketProvider(),
    GenericHttpsProvider(),
]


def resolve_location(base: str | Path | None, target: str) -> str | Path:
    """Resolve `target` (URL or relative/absolute path) against `base` (config file Path or URL)."""
    if is_url(target):
        return target
    if base is None:
        return Path(target)
    if is_url(base):
        return RemoteFile.parse(str(base)).resolve_relative(target)
    base_path = Path(base)
    base_dir = base_path if base_path.is_dir() else base_path.parent
    return (base_dir / target).resolve()


class RemoteCache:
    """Simple TTL file cache for remote fetches. Never stores credentials."""

    def __init__(self, ttl: float = 0.0, directory: str | Path | None = None):
        self.ttl = max(0.0, float(ttl))
        if directory is not None:
            self.directory = Path(directory)
        else:
            xdg = os.environ.get("XDG_CACHE_HOME")
            base = Path(xdg) if xdg else Path.home() / ".cache"
            self.directory = base / "catalog-parser"

    def _entry_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, url: str) -> bytes | None:
        if self.ttl <= 0:
            return None
        path = self._entry_path(url)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(payload["timestamp"]) <= self.ttl:
                return str(payload["content"]).encode("utf-8")
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return None

    def put(self, url: str, text: str) -> None:
        if self.ttl <= 0:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            payload = {"url": url, "timestamp": time.time(), "content": text}
            self._entry_path(url).write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass


class RemoteConfigLoader:
    def __init__(
        self,
        fetch: Fetcher = urllib_fetch,
        token: str | None = None,
        timeout: float = REQUEST_TIMEOUT,
        auth_header: str | None = None,
        cache: RemoteCache | None = None,
    ):
        self.fetch = fetch
        self.token = token if token is not None else os.environ.get(TOKEN_ENV)
        self.timeout = timeout
        self.auth_header = auth_header if auth_header is not None else os.environ.get(AUTH_HEADER_ENV)
        if cache is not None:
            self.cache = cache
        else:
            raw_ttl = os.environ.get(CACHE_TTL_ENV, "0")
            try:
                ttl = float(raw_ttl)
            except ValueError:
                ttl = 0.0
            self.cache = RemoteCache(ttl=ttl, directory=os.environ.get(CACHE_DIR_ENV))

    def read(self, location: str) -> tuple[str, str]:
        """(text, file name) of the resource at `location`."""
        remote = RemoteFile.parse(location)
        if self.token and remote.url.startswith("http://"):
            raise RemoteError(f"refusing to send ${TOKEN_ENV} over plain http: {location}")
        cached = self.cache.get(remote.url)
        if cached is not None:
            return cached.decode("utf-8"), remote.name
        try:
            data = self.fetch(remote.url, remote.headers(self.token, self.auth_header), self.timeout)
        except FetchError as e:
            raise RemoteError(self._explain(location, e)) from None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise RemoteError(f"config at {location} is not UTF-8 text") from None
        self.cache.put(remote.url, text)
        return text, remote.name

    def _explain(self, location: str, error: FetchError) -> str:
        message = f"cannot read config {location}: {error}"
        if error.status in (401, 403):
            return f"{message} (check ${TOKEN_ENV}: missing, expired, or without read access)"
        if error.status == 404:
            hint = "" if self.token else f"; set ${TOKEN_ENV} if the project is private"
            return f"{message} (wrong URL or ref, or no access: host may answer 404 for private projects{hint})"
        return message
