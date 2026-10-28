from __future__ import annotations

import pytest
from conftest import base, codes, component, write

from catalog_parser import ConfigError, Settings, check_repo, lint_file
from catalog_parser.cli import diagram_main, main
from catalog_parser.config import CONFIG_ENV, find_config

CLOSED = """
[vocabulary]
technologies = ["rest-api", "oracle"]
"""


@pytest.fixture(autouse=True)
def _no_env_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)


def repo(tmp_path, data):
    """A repository folder (with .git, the config search boundary) holding `data`."""
    path = write(tmp_path, data)
    (path.parents[1] / ".git").mkdir()
    return path.parents[1]


def test_defaults():
    s = Settings()
    assert s.vocabulary.technologies is None and s.vocabulary.criticalities == ("high", "medium", "low")
    assert s.layout.catalog_dir == "catalog" and s.layout.peers_env == "CATALOG_PEERS"
    assert s.rules.enabled("E110") and s.diagram.direction == "LR" and s.source is None


def test_open_vocabulary_accepts_any_technology_and_git_provider(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka", protocol="amqp")]
    d["git"]["type"] = "github"
    assert lint_file(write(tmp_path, d)).issues == []


def test_closed_vocabulary_rejects_with_e002_on_the_line(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    parsed = lint_file(write(tmp_path, d), Settings.from_mapping({"vocabulary": {"technologies": ["rest-api"]}}))
    (issue,) = parsed.issues
    assert issue.code == "E002" and issue.location == "components[0].technology" and issue.line
    assert "kafka" in issue.message and "rest-api" in issue.message


def test_custom_criticalities(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", criticality="tier-1")]
    settings = Settings.from_mapping({"vocabulary": {"criticalities": ["tier-1", "tier-2"]}})
    assert lint_file(write(tmp_path, d), settings).issues == []
    assert codes(lint_file(write(tmp_path, d)).issues) == {"E002"}


def test_dot_file_is_discovered_from_the_repo(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    root = repo(tmp_path, d)
    assert check_repo(root, peers=[]) == []
    (root / ".catalog-parser.toml").write_text(CLOSED)
    assert codes(check_repo(root, peers=[])) == {"E002"}


def test_pyproject_table_is_discovered(tmp_path):
    root = repo(tmp_path, base("svc-a"))
    (root / "pyproject.toml").write_text('[project]\nname = "x"\n')
    assert find_config(root) is None  # a pyproject without the table is not a config
    (root / "pyproject.toml").write_text('[tool.catalog-parser.rules]\nignore = ["E110"]\n')
    assert find_config(root) == root / "pyproject.toml"
    assert not Settings.discover(root).rules.enabled("E110")


def test_search_stops_at_the_repository_boundary(tmp_path):
    (tmp_path / ".catalog-parser.toml").write_text(CLOSED)
    root = repo(tmp_path, base("svc-a"))
    assert find_config(root) is None


def test_environment_variable_wins(tmp_path, monkeypatch):
    cfg = tmp_path / "shared.toml"
    cfg.write_text(CLOSED)
    monkeypatch.setenv(CONFIG_ENV, str(cfg))
    assert Settings.discover(tmp_path).source == cfg


@pytest.mark.parametrize("text, message", [
    ("[vocabulary]\ntechnology = []\n", "unknown key"),
    ("[colours]\n", "unknown section"),
    ("[vocabulary]\ntechnologies = 'x'\n", "list of non-empty strings"),
    ("[vocabulary]\ndata_categories = ['blob']\n", "not in categories"),
    ("[diagram]\ndirection = 'up'\n", "direction"),
    ("not toml", "cannot read config"),
])
def test_invalid_config(tmp_path, text, message):
    cfg = tmp_path / ".catalog-parser.toml"
    cfg.write_text(text)
    with pytest.raises(ConfigError, match=message):
        Settings.from_file(cfg)


def test_cli_config_option_and_usage_error(tmp_path, capsys):
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    write(tmp_path, d)
    cfg = tmp_path / "c.toml"
    cfg.write_text(CLOSED)
    assert main([str(tmp_path)]) == 0
    assert main(["--config", str(cfg), str(tmp_path)]) == 1
    cfg.write_text("[nope]\n")
    assert main(["--config", str(cfg), str(tmp_path)]) == 2
    assert diagram_main([str(tmp_path / "svc-a"), "--config", str(cfg)]) == 2
    assert "unknown section" in capsys.readouterr().err


def test_cli_discovers_from_the_working_directory(tmp_path, monkeypatch):
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    root = repo(tmp_path, d)
    (root / ".catalog-parser.toml").write_text(CLOSED)
    monkeypatch.chdir(root)
    assert main(["."]) == 1


def test_diagram_settings_from_config_and_cli_overrides(tmp_path):
    root = repo(tmp_path, base("svc-a"))
    (root / "docs").mkdir()
    (root / ".catalog-parser.toml").write_text('[diagram]\nsubdir = "arch"\nfilename = "map.md"\n')
    assert diagram_main([str(root)]) == 0
    assert (root / "docs" / "arch" / "map.md").exists()
    assert diagram_main([str(root), "--filename", "other.md"]) == 0
    assert (root / "docs" / "arch" / "other.md").exists()
