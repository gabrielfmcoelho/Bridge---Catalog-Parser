from __future__ import annotations

import pytest
from conftest import base, codes, component, external, write

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
    assert s.vocabulary.entity_types is None
    assert s.schema.required_fields == frozenset({"owners", "entity", "git"})
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


def test_entity_types_and_custom_vocabulary(tmp_path):
    d = base("svc-a")
    d["entity"][0]["type"] = "department"
    settings = Settings.from_mapping({
        "vocabulary": {
            "entity_types": ["company", "squad"],
            "custom": {"tier": ["gold", "silver"]},
        }
    })
    parsed = lint_file(write(tmp_path, d), settings)
    assert codes(parsed.issues) == {"E002"}
    assert parsed.issues[0].location == "entity[0].type"
    assert settings.vocabulary.check("tier", "gold") == "gold"
    with pytest.raises(ValueError, match="tier 'bronze' is not one of: gold, silver"):
        settings.vocabulary.check("tier", "bronze")


def test_custom_criticalities(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", criticality="tier-1")]
    settings = Settings.from_mapping({"vocabulary": {"criticalities": ["tier-1", "tier-2"]}})
    assert lint_file(write(tmp_path, d), settings).issues == []
    assert codes(lint_file(write(tmp_path, d)).issues) == {"E002"}


def test_schema_required_fields_and_optional_entity_or_git(tmp_path):
    d = base("svc-a")
    del d["entity"]
    del d["git"]
    path = write(tmp_path, d)
    # By default, entity and git are required -> E002
    default_issues = lint_file(path).issues
    assert codes(default_issues) == {"E002"}
    assert {i.location for i in default_issues} == {"entity", "git"}

    # When configured to only require owners, omitting entity and git is valid (and E110 is skipped)
    relaxed = Settings.from_mapping({"schema": {"required_fields": ["owners"]}})
    assert lint_file(path, relaxed).issues == []


def test_schema_custom_slug_pattern_metadata_and_extra_fields(tmp_path):
    d = base("svc_a.v1")
    d["git"]["path"] = "group/svc_a.v1"
    d["custom_top_level"] = "allowed-when-configured"
    path = write(tmp_path, d)
    assert codes(lint_file(path).issues) == {"E002"}

    settings = Settings.from_mapping({
        "schema": {
            "slug_pattern": r"^[a-z0-9][a-z0-9._-]*$",
            "required_metadata": ["domain", "squad"],
            "allow_extra_fields": True,
        }
    })
    # Missing required metadata keys -> E002 on metadata
    issues = lint_file(path, settings).issues
    assert codes(issues) == {"E002"} and issues[0].location == "metadata"

    d["metadata"] = {"domain": "payments", "squad": "checkout"}
    assert lint_file(write(tmp_path, d), settings).issues == []


def test_schema_custom_external_required_traits(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [{"ci": "ext-api", "technology": "rest-api"}]
    path = write(tmp_path, d)
    assert "E104" in codes(lint_file(path).issues)

    # Only require 'technology' on external upstream entries
    minimal = Settings.from_mapping({"schema": {"external_required_traits": ["technology"]}})
    assert lint_file(path, minimal).issues == []


def test_rule_severity_overrides_in_config(tmp_path):
    d = base("svc-a")
    d["git"]["path"] = "group/mismatch"                    # E110 (default: error)
    d["components"] = [component("api", protocol=None)]    # W201 (default: warning)
    path = write(tmp_path, d)

    cfg = tmp_path / ".catalog-parser.toml"
    cfg.write_text('[rules.severity]\nE110 = "warning"\nW201 = "error"\n')
    settings = Settings.from_file(cfg)
    by_code = {i.code: i.severity for i in lint_file(path, settings).issues}
    assert by_code == {"E110": "warning", "W201": "error"}

    # With E110 demoted to warning and W201 ignored, CLI exits 0 without --strict
    cfg.write_text('[rules]\nignore = ["W201"]\n[rules.severity]\nE110 = "warning"\n')
    assert main(["--config", str(cfg), str(path)]) == 0


def test_extends_local_inheritance_and_circular_detection(tmp_path):
    base_cfg = tmp_path / "base.toml"
    Child_cfg = tmp_path / "child.toml"
    base_cfg.write_text(
        '[vocabulary]\ntechnologies = ["postgresql"]\n'
        '[rules]\nignore = ["E110"]\n'
        '[diagram.styles]\nhigh = "fill:#111"\n'
    )
    Child_cfg.write_text(
        'extends = "./base.toml"\n'
        '[rules]\nignore = ["W201"]\n'
        '[diagram.styles]\nlow = "fill:#222"\n'
    )
    s = Settings.from_file(Child_cfg)
    assert s.vocabulary.technologies == frozenset({"postgresql"})
    assert s.rules.ignore == frozenset({"E110", "W201"})
    assert s.diagram.styles["high"] == "fill:#111" and s.diagram.styles["low"] == "fill:#222"

    # Circular extends raises ConfigError
    base_cfg.write_text('extends = "./child.toml"\n')
    with pytest.raises(ConfigError, match="circular config 'extends'"):
        Settings.from_file(Child_cfg)


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
    ("[schema]\nslug_pattern = '['\n", "invalid regex"),
    ("[schema]\nrequired_fields = ['unknown']\n", "unknown field"),
    ("[rules.severity]\nE110 = 'fatal'\n", "invalid severity"),
    ("locked = ['nope']\n", "unknown section"),
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
