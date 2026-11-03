from __future__ import annotations

import pytest
from conftest import base, component, write

from catalog_parser import ConfigError, Settings, check_repo
from catalog_parser.cli import main
from catalog_parser.dotenv import catalog_env, find_dotenv, parse_dotenv

CLOSED = '[vocabulary]\ntechnologies = ["rest-api"]\n'


def test_parse_format():
    text = """
# comment
export CATALOG_PARSER_CONFIG="https://gitlab.example/g/p/-/blob/main/.catalog-parser.toml"
CATALOG_PARSER_TOKEN='glpat-abc # not a comment'
PLAIN=value # trailing comment
EMPTY=
not a variable
"""
    assert parse_dotenv(text) == {
        "CATALOG_PARSER_CONFIG": "https://gitlab.example/g/p/-/blob/main/.catalog-parser.toml",
        "CATALOG_PARSER_TOKEN": "glpat-abc # not a comment",
        "PLAIN": "value",
        "EMPTY": "",
    }


def test_only_prefixed_keys_and_environment_wins(tmp_path):
    (tmp_path / ".env").write_text("CATALOG_PARSER_TOKEN=from-file\nCATALOG_PARSER_CONFIG=x\nDB_PASSWORD=secret\n")
    env = catalog_env(tmp_path, environ={"CATALOG_PARSER_TOKEN": "from-env", "HOME": "/h"})
    assert env == {"CATALOG_PARSER_TOKEN": "from-env", "CATALOG_PARSER_CONFIG": "x"}


def test_found_from_a_subfolder_up_to_the_repository_boundary(tmp_path):
    (tmp_path / ".env").write_text("CATALOG_PARSER_CONFIG=outside\n")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "catalog").mkdir()
    assert find_dotenv(repo / "catalog") is None            # stops at the repo's .git
    (repo / ".env").write_text("CATALOG_PARSER_CONFIG=inside\n")
    assert find_dotenv(repo / "catalog") == repo / ".env"
    assert catalog_env(repo / "catalog", environ={}) == {"CATALOG_PARSER_CONFIG": "inside"}


@pytest.fixture
def repo(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    root = write(tmp_path, d).parents[1]
    (root / ".git").mkdir()
    (tmp_path / "rules.toml").write_text(CLOSED)
    return root


def test_cli_reads_the_config_location_from_dotenv(repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert main(["."]) == 0                                  # no .env: open vocabulary
    (repo / ".env").write_text(f"CATALOG_PARSER_CONFIG={repo.parent / 'rules.toml'}\n")
    assert main(["."]) == 1


def test_check_repo_and_pytest_helper_read_dotenv_from_the_repo(repo):
    (repo / ".env").write_text(f"CATALOG_PARSER_CONFIG={repo.parent / 'rules.toml'}\n")
    assert {i.code for i in check_repo(repo, peers=[])} == {"E002"}


def test_token_comes_from_dotenv(repo):
    """The token in .env reaches the remote loader: proven by the plain-http refusal, without a network."""
    (repo / ".env").write_text("CATALOG_PARSER_CONFIG=http://intranet/.catalog-parser.toml\nCATALOG_PARSER_TOKEN=t\n")
    with pytest.raises(ConfigError, match="plain http"):
        Settings.discover(repo)
