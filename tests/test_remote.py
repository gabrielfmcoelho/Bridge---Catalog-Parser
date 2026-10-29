from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import base, component, write

from catalog_parser import ConfigError, Settings, check_repo
from catalog_parser.cli import main
from catalog_parser.config import CONFIG_ENV
from catalog_parser.remote import TOKEN_ENV, FetchError, RemoteConfigLoader, RemoteFile

CLOSED = '[vocabulary]\ntechnologies = ["rest-api"]\n'
PAGE = "https://gitlab.example/org/2.-produtos/governance/-/blob/v1/rules/.catalog-parser.toml"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    monkeypatch.delenv(TOKEN_ENV, raising=False)


class FakeFetch:
    def __init__(self, body: str = CLOSED, error: FetchError | None = None):
        self.body, self.error, self.calls = body, error, []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers)))
        if self.error:
            raise self.error
        return self.body.encode()


def test_gitlab_page_becomes_the_files_api_call():
    r = RemoteFile.parse(PAGE)
    assert r.url == ("https://gitlab.example/api/v4/projects/org%2F2.-produtos%2Fgovernance"
                     "/repository/files/rules%2F.catalog-parser.toml/raw?ref=v1")
    assert r.name == ".catalog-parser.toml" and r.headers("t") == {"PRIVATE-TOKEN": "t"}
    assert RemoteFile.parse(PAGE.replace("/-/blob/", "/-/raw/")).url == r.url


def test_api_url_and_other_hosts():
    api = RemoteFile.parse("https://gitlab.example/api/v4/projects/7/repository/files/a%2Fpyproject.toml/raw?ref=main")
    assert api.url.endswith("ref=main") and api.name == "pyproject.toml" and api.headers("t") == {"PRIVATE-TOKEN": "t"}
    gh = RemoteFile.parse("https://raw.githubusercontent.com/o/r/main/.catalog-parser.toml")
    assert gh.headers("t") == {"Authorization": "Bearer t"} and gh.headers(None) == {}


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
def server():
    """Serves CLOSED at /.catalog-parser.toml; any other path is 404. Records the request headers."""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(dict(self.headers))
            if self.path != "/.catalog-parser.toml":
                self.send_error(404)
                return
            body = CLOSED.encode()
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
