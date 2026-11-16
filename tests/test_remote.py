from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml
from conftest import base, codes, component, write

from catalog_parser import ConfigError, Settings, check_repo
from catalog_parser.cli import diagram_main, main
from catalog_parser.config import CONFIG_ENV
from catalog_parser.remote import (
    AUTH_HEADER_ENV,
    CACHE_DIR_ENV,
    CACHE_TTL_ENV,
    TOKEN_ENV,
    FetchError,
    RemoteCache,
    RemoteConfigLoader,
    RemoteFile,
    resolve_location,
)

CLOSED = '[vocabulary]\ntechnologies = ["rest-api"]\n'
PAGE = "https://gitlab.example/org/2.-produtos/governance/-/blob/v1/rules/.catalog-parser.toml"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (CONFIG_ENV, TOKEN_ENV, AUTH_HEADER_ENV, CACHE_TTL_ENV, CACHE_DIR_ENV):
        monkeypatch.delenv(var, raising=False)


class FakeFetch:
    def __init__(self, body: str | dict[str, str] = CLOSED, error: FetchError | None = None):
        self.body, self.error, self.calls = body, error, []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers)))
        if self.error:
            raise self.error
        if isinstance(self.body, dict):
            if url not in self.body:
                raise FetchError("HTTP 404 Not Found", 404)
            return self.body[url].encode()
        return self.body.encode()


def test_gitlab_page_becomes_the_files_api_call():
    r = RemoteFile.parse(PAGE)
    assert r.url == (
        "https://gitlab.example/api/v4/projects/org%2F2.-produtos%2Fgovernance"
        "/repository/files/rules%2F.catalog-parser.toml/raw?ref=v1"
    )
    assert r.name == ".catalog-parser.toml" and r.headers("t") == {"PRIVATE-TOKEN": "t"}
    assert r.provider == "gitlab" and r.gitlab is True
    assert RemoteFile.parse(PAGE.replace("/-/blob/", "/-/raw/")).url == r.url


def test_github_and_bitbucket_pages_and_api_urls():
    gh_page = RemoteFile.parse("https://github.com/acme/governance/blob/v2/configs/.catalog-parser.toml")
    assert gh_page.url == "https://raw.githubusercontent.com/acme/governance/v2/configs/.catalog-parser.toml"
    assert gh_page.name == ".catalog-parser.toml" and gh_page.provider == "github" and not gh_page.gitlab
    assert gh_page.headers("tok") == {"Authorization": "Bearer tok"}

    gh_api = RemoteFile.parse("https://api.github.com/repos/acme/governance/contents/configs/.catalog-parser.toml?ref=v2")
    assert gh_api.provider == "github" and gh_api.name == ".catalog-parser.toml"
    assert gh_api.headers("tok") == {
        "Accept": "application/vnd.github.raw+json",
        "Authorization": "Bearer tok",
    }

    bb_page = RemoteFile.parse("https://bitbucket.org/acme/governance/src/main/rules/.catalog-parser.toml")
    assert bb_page.url == "https://api.bitbucket.org/2.0/repositories/acme/governance/src/main/rules/.catalog-parser.toml"
    assert bb_page.name == ".catalog-parser.toml" and bb_page.provider == "bitbucket"
    assert bb_page.headers("tok") == {"Authorization": "Bearer tok"}


def test_api_url_and_other_hosts():
    api = RemoteFile.parse("https://gitlab.example/api/v4/projects/7/repository/files/a%2Fpyproject.toml/raw?ref=main")
    assert api.url.endswith("ref=main") and api.name == "pyproject.toml" and api.headers("t") == {"PRIVATE-TOKEN": "t"}
    gh = RemoteFile.parse("https://raw.githubusercontent.com/o/r/main/.catalog-parser.toml")
    assert gh.headers("t") == {"Authorization": "Bearer t"} and gh.headers(None) == {}
    assert gh.headers("t", auth_header="X-Custom-Token") == {"X-Custom-Token": "t"}


def test_resolve_relative_urls_across_providers():
    # GitLab blob URL
    gl = RemoteFile.parse(PAGE)
    assert gl.resolve_relative("./base.toml") == (
        "https://gitlab.example/org/2.-produtos/governance/-/blob/v1/rules/base.toml"
    )
    assert gl.resolve_relative("../common/vocab.toml") == (
        "https://gitlab.example/org/2.-produtos/governance/-/blob/v1/common/vocab.toml"
    )

    # GitLab API URL with %2F-encoded file path
    gl_api = RemoteFile.parse(
        "https://gitlab.example/api/v4/projects/org%2Fgov/repository/files/rules%2Fteam%2Fcfg.toml/raw?ref=v1"
    )
    assert gl_api.resolve_relative("../base.toml") == (
        "https://gitlab.example/api/v4/projects/org%2Fgov/repository/files/rules%2Fbase.toml/raw?ref=v1"
    )

    # GitHub blob URL
    gh = RemoteFile.parse("https://github.com/acme/gov/blob/main/teams/payments.toml")
    assert resolve_location(gh.location, "../base.toml") == "https://github.com/acme/gov/blob/main/base.toml"


def test_remote_cache_ttl(tmp_path):
    fetch = FakeFetch()
    cache = RemoteCache(ttl=60.0, directory=tmp_path / "cache")
    loader = RemoteConfigLoader(fetch, cache=cache)
    s1 = Settings.load("https://raw.githubusercontent.com/o/r/main/.catalog-parser.toml", loader)
    s2 = Settings.load("https://raw.githubusercontent.com/o/r/main/.catalog-parser.toml", loader)
    assert s1.vocabulary.technologies == frozenset({"rest-api"})
    assert s2.vocabulary.technologies == frozenset({"rest-api"})
    assert len(fetch.calls) == 1  # second call was served from cache


def test_remote_extends_and_locked_governance():
    base_url = "https://github.com/acme/gov/blob/v1/base.toml"
    team_url = "https://github.com/acme/gov/blob/v1/teams/payments.toml"
    raw_base = "https://raw.githubusercontent.com/acme/gov/v1/base.toml"
    raw_team = "https://raw.githubusercontent.com/acme/gov/v1/teams/payments.toml"

    files = {
        raw_base: (
            'locked = ["vocabulary"]\n'
            '[vocabulary]\n'
            'technologies = ["rest-api", "postgresql"]\n'
            '[diagram]\n'
            'direction = "TB"\n'
        ),
        raw_team: (
            'extends = "../base.toml"\n'
            '[diagram]\n'
            'docs_dir = "architecture"\n'
        ),
    }
    fetch = FakeFetch(files)
    settings = Settings.load(team_url, RemoteConfigLoader(fetch))
    assert settings.vocabulary.technologies == frozenset({"rest-api", "postgresql"})
    assert settings.diagram.direction == "TB"
    assert settings.diagram.docs_dir == "architecture"
    assert "vocabulary" in settings.locked

    # Trying to override a locked section from a child config must fail
    bad_child = 'extends = "../base.toml"\n[vocabulary]\ntechnologies = ["kafka"]\n'
    files[raw_team] = bad_child
    with pytest.raises(ConfigError, match=r"section \[vocabulary\] is locked"):
        Settings.load(team_url, RemoteConfigLoader(FakeFetch(files)))


def test_settings_from_url_sends_the_token_from_the_environment(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "secret")
    fetch = FakeFetch()
    settings = Settings.load(PAGE, RemoteConfigLoader(fetch))
    assert settings.vocabulary.technologies == frozenset({"rest-api"}) and settings.source == PAGE
    ((url, headers),) = fetch.calls
    assert "/api/v4/projects/" in url and headers == {"PRIVATE-TOKEN": "secret"}


def test_remote_pyproject_uses_its_tool_table():
    fetch = FakeFetch('[tool.catalog-parser.rules]\nignore = ["E110"]\n')
    url = "https://gitlab.example/org/repo/-/blob/main/pyproject.toml"
    assert not Settings.load(url, RemoteConfigLoader(fetch)).rules.enabled("E110")


@pytest.mark.parametrize("error, token, hint", [
    (FetchError("HTTP 401 Unauthorized", 401), "t", TOKEN_ENV),
    (FetchError("HTTP 404 Not Found", 404), None, f"set ${TOKEN_ENV}"),
    (FetchError("timed out"), "t", "timed out"),
])
def test_errors_explain_and_never_show_the_token(error, token, hint):
    with pytest.raises(ConfigError) as exc:
        Settings.load(PAGE, RemoteConfigLoader(FakeFetch(error=error), token=token))
    assert hint in str(exc.value) and PAGE in str(exc.value) and "secret" not in str(exc.value)


def test_token_is_never_sent_over_plain_http():
    fetch = FakeFetch()
    with pytest.raises(ConfigError, match="plain http"):
        Settings.load("http://intranet/.catalog-parser.toml", RemoteConfigLoader(fetch, token="t"))
    assert fetch.calls == []


@pytest.fixture
def server(pair):
    """Serves a remote governance repository with config and peer catalogs over HTTP."""
    seen: list[dict] = []
    a, _ = pair
    peer_yaml = yaml.safe_dump(a, sort_keys=False)
    gov_config = (
        '[vocabulary]\n'
        'technologies = ["rest-api"]\n'
        '[layout]\n'
        'peers = ["./peers/svc-a.yml"]\n'
    )
    routes = {
        "/.catalog-parser.toml": CLOSED,
        "/gov/.catalog-parser.toml": gov_config,
        "/gov/peers/svc-a.yml": peer_yaml,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(dict(self.headers))
            if self.path not in routes:
                self.send_error(404)
                return
            body = routes[self.path].encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


def test_cli_and_check_repo_read_the_rules_from_the_url(tmp_path, monkeypatch, server, capsys):
    root, seen = server
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    write(tmp_path, d)
    assert main([str(tmp_path)]) == 0                                        # no config: open vocabulary
    assert main(["--config", f"{root}/.catalog-parser.toml", str(tmp_path)]) == 1
    monkeypatch.setenv(CONFIG_ENV, f"{root}/.catalog-parser.toml")
    assert main([str(tmp_path)]) == 1
    assert {i.code for i in check_repo(tmp_path / "svc-a", peers=[])} == {"E002"}
    assert all("Authorization" not in h and "Private-Token" not in h for h in seen)   # no token set
    monkeypatch.setenv(CONFIG_ENV, f"{root}/missing.toml")
    assert main([str(tmp_path)]) == 2
    assert "404" in capsys.readouterr().err


def test_remote_peers_from_governance_repository(tmp_path, pair, server, capsys):
    root, _ = server
    _, b = pair
    fb = write(tmp_path, b)
    repo_b = fb.parents[1]
    (repo_b / ".git").mkdir()
    # Local repo extends the remote governance config, which also provides svc-a as a remote peer!
    (repo_b / ".catalog-parser.toml").write_text(f'extends = "{root}/gov/.catalog-parser.toml"\n')

    # Without peers, svc-b gets W203; with the remote peer from the governance config, it passes cleanly!
    assert codes(check_repo(repo_b, peers=[])) == {"W203"}
    assert check_repo(repo_b) == []

    # And catalog-diagram resolves svc-a's protocol/port from the remote peer!
    assert diagram_main([str(repo_b), "--stdout"]) == 0
    assert 'svc_b_client -->|"http:8000"| svc_a_api' in capsys.readouterr().out
