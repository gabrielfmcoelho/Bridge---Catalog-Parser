"""Config files read over HTTPS, so the rules can live in a repository that nobody has to clone.

`location` is a URL:

- a GitLab file page, as copied from the browser (`https://host/group/project/-/blob/<ref>/<path>`,
  or `/-/raw/`): it is turned into the files API call
  (`/api/v4/projects/<project>/repository/files/<path>/raw?ref=<ref>`) and authenticated with
  `PRIVATE-TOKEN`, which needs a token with the `read_api` scope;
- a GitLab API URL (`.../api/v4/...`): fetched as-is, with `PRIVATE-TOKEN`;
- any other URL (e.g. raw.githubusercontent.com): fetched as-is, with `Authorization: Bearer`.

The token comes from $CATALOG_PARSER_TOKEN, never from the command line (shell history), and is
never sent over plain http. The network call is the injectable `fetch`, so the loader is tested
without a network.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse

TOKEN_ENV = "CATALOG_PARSER_TOKEN"
REQUEST_TIMEOUT = 30

_GITLAB_PAGE = re.compile(r"^(?P<base>https?://[^/]+)/(?P<project>[^?#]+?)/-/(?:blob|raw)/(?P<ref>[^/]+)/(?P<path>[^?#]+)")
_GITLAB_API_FILE = re.compile(r"/api/v4/projects/[^/]+/repository/files/(?P<path>[^/]+)/raw")


class RemoteError(Exception):
    """A remote config could not be read; the message never contains the token."""


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
    gitlab: bool

    @classmethod
    def parse(cls, location: str) -> RemoteFile:
        page = _GITLAB_PAGE.match(location)
        if page:
            project, path = page["project"].strip("/"), unquote(page["path"])
            url = (f"{page['base']}/api/v4/projects/{quote(project, safe='')}/repository/files/"
                   f"{quote(path, safe='')}/raw?ref={quote(page['ref'], safe='')}")
            return cls(location, url, path.rsplit("/", 1)[-1], gitlab=True)
        api = _GITLAB_API_FILE.search(location)
        if api:
            return cls(location, location, unquote(api["path"]).rsplit("/", 1)[-1], gitlab=True)
        if "/api/v4/" in location:
            return cls(location, location, "", gitlab=True)
        return cls(location, location, urlparse(location).path.rsplit("/", 1)[-1], gitlab=False)

    def headers(self, token: str | None) -> dict[str, str]:
        if not token:
            return {}
        return {"PRIVATE-TOKEN": token} if self.gitlab else {"Authorization": f"Bearer {token}"}


class RemoteConfigLoader:
    def __init__(self, fetch: Fetcher = urllib_fetch, token: str | None = None, timeout: float = REQUEST_TIMEOUT):
        self.fetch = fetch
        self.token = token if token is not None else os.environ.get(TOKEN_ENV)
        self.timeout = timeout

    def read(self, location: str) -> tuple[str, str]:
        """(text, file name) of the config at `location`."""
        remote = RemoteFile.parse(location)
        if self.token and remote.url.startswith("http://"):
            raise RemoteError(f"refusing to send ${TOKEN_ENV} over plain http: {location}")
        try:
            data = self.fetch(remote.url, remote.headers(self.token), self.timeout)
        except FetchError as e:
            raise RemoteError(self._explain(location, e)) from None
        try:
            return data.decode("utf-8"), remote.name
        except UnicodeDecodeError:
            raise RemoteError(f"config at {location} is not UTF-8 text") from None

    def _explain(self, location: str, error: FetchError) -> str:
        message = f"cannot read config {location}: {error}"
        if error.status in (401, 403):
            return f"{message} (check ${TOKEN_ENV}: missing, expired, or without read access)"
        if error.status == 404:
            hint = "" if self.token else f"; set ${TOKEN_ENV} if the project is private"
            return f"{message} (wrong URL or ref, or no access: GitLab answers 404 for private projects{hint})"
        return message
