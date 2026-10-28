from __future__ import annotations

import io
import json
from pathlib import Path

import yaml
from conftest import base, codes, component, write
from pydantic import BaseModel, ConfigDict

from catalog_parser import (
    CatalogKind,
    DiagramSettings,
    FileRule,
    Finding,
    Layout,
    Linter,
    MermaidRenderer,
    Reporter,
    RuleSelection,
    Settings,
    Vocabulary,
    check_repo,
    default_registry,
    lint_file,
)
from catalog_parser.cli import main
from catalog_parser.issues import WARNING, RuleInfo
from catalog_parser.reporters import REPORTERS


def test_ignore_and_select(tmp_path):
    d = base("svc-a")
    d["git"]["path"] = "group/other"                       # E110
    d["components"] = [component("api", protocol=None)]    # W201
    path = write(tmp_path, d)
    assert codes(lint_file(path).issues) == {"E110", "W201"}
    assert codes(lint_file(path, Settings(rules=RuleSelection(ignore=frozenset({"E110"})))).issues) == {"W201"}
    assert codes(lint_file(path, Settings(rules=RuleSelection(select=frozenset({"E1"})))).issues) == {"E110"}
    assert main(["--ignore", "E110,W201", str(tmp_path)]) == 0
    assert main(["--select", "W", "--strict", str(tmp_path)]) == 1


def test_custom_catalog_dir(tmp_path, pair):
    a, b = pair
    layout = Layout(catalog_dir=".meta/deps")
    for d in (a, b):
        f = tmp_path / d["ci"] / ".meta" / "deps" / "dependencies.yml"
        f.parent.mkdir(parents=True)
        f.write_text(yaml.safe_dump(d), encoding="utf-8")
    settings = Settings(layout=layout)
    assert len(Linter(settings).discoverer.discover([tmp_path])) == 2
    assert Linter(Settings()).discoverer.discover([tmp_path]) == []
    assert check_repo(tmp_path / "svc-b", peers=[tmp_path], settings=settings) == []
    explicit = tmp_path / "svc-b" / ".meta" / "deps" / "dependencies.yml"
    from catalog_parser import Repository
    assert Repository(explicit, layout).root == tmp_path / "svc-b"


def test_skip_dirs_only_apply_below_the_searched_folder(tmp_path, pair):
    build = tmp_path / "build"  # a skipped name ABOVE the searched folder must not hide the catalogs
    for d in pair:
        write(build, d)
    assert len(Linter().discoverer.discover([build])) == 2
    write(build / "svc-a" / "node_modules" / "pkg", pair[0])
    assert len(Linter().discoverer.discover([build])) == 2


def test_peers_env_name_is_configurable(tmp_path, pair, monkeypatch):
    a, b = pair
    a["dependencies"]["downstream"] = []
    write(tmp_path, a)
    fb = write(tmp_path, b)
    monkeypatch.setenv("MY_PEERS", str(tmp_path))
    settings = Settings(layout=Layout(peers_env="MY_PEERS"))
    assert codes(check_repo(fb.parents[1], settings=settings)) == {"X003"}


class Owners(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team: str
    oncall: list[str] = []


class NeedsOncall(FileRule):
    info = RuleInfo("O101", WARNING, "team without on-call")

    def check(self, catalog, vocabulary):
        if not catalog.oncall:
            yield Finding(("team",), f"team '{catalog.team}' has no on-call")


def test_register_a_new_catalog_kind(tmp_path):
    f = tmp_path / "svc" / "catalog" / "owners.yml"
    f.parent.mkdir(parents=True)
    f.write_text("team: core\n")
    assert codes(Linter().lint_paths([tmp_path])) == set()  # not registered: not discovered
    registry = default_registry()
    registry.register(CatalogKind("owners.yml", Owners, file_rules=(NeedsOncall(),)))
    (issue,) = Linter(registry=registry).lint_paths([tmp_path])
    assert (issue.code, issue.line, issue.location) == ("O101", 1, "team")
    assert main(["--list-rules"], registry=registry) == 0


def test_cli_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    out = capsys.readouterr().out
    assert "X003  error" in out and "W203  warning" in out and "E001" in out


class CountReporter(Reporter):
    def report(self, issues, out, err):
        print(len(issues), file=out)


def test_custom_reporter(monkeypatch, tmp_path, pair, capsys):
    a, b = pair
    a["dependencies"]["downstream"] = []
    write(tmp_path, a), write(tmp_path, b)
    monkeypatch.setitem(REPORTERS, "count", CountReporter)
    assert main(["--format", "count", str(tmp_path)]) == 1
    assert capsys.readouterr().out == "1\n"
    buf = io.StringIO()
    REPORTERS["json"]().report(Linter().lint_paths([tmp_path]), buf, io.StringIO())
    assert json.loads(buf.getvalue())[0]["severity"] == "error"


def test_diagram_direction_styles_and_data_categories(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", criticality="tier-1"),
                       component("lake", category="storage", technology="s3", criticality="tier-2",
                                 protocol=None, port=None)]
    vocabulary = Vocabulary(categories=frozenset({"application", "storage"}), data_categories=frozenset({"storage"}),
                            criticalities=("tier-1", "tier-2"))
    settings = Settings(vocabulary=vocabulary)
    catalog = lint_file(write(tmp_path, d), settings).catalog
    text = MermaidRenderer(DiagramSettings(direction="TB", styles={"tier-1": "fill:#f00"}), vocabulary).render(catalog)
    assert text.startswith("flowchart TB")
    assert 'svc_a_lake[("lake<br/>s3")]' in text
    assert "classDef tier-1 fill:#f00" in text and "class svc_a_api tier-1" in text
    assert "tier-2" not in text  # no style configured for it: no class line


def test_diagram_title_and_legend(tmp_path, pair):
    _, b = pair
    root = write(tmp_path, b).parents[1]
    (root / "docs").mkdir()
    (root / ".git").mkdir()
    (root / ".catalog-parser.toml").write_text('[diagram]\ntitle = "Map of {ci}"\nlegend = "Custom legend."\n')
    from catalog_parser import generate_diagram
    text = generate_diagram(root).path.read_text()
    assert "# Map of svc-b" in text and text.endswith("Custom legend.\n")


def test_peer_settings_do_not_leak_between_linters(tmp_path):
    """Each Linter carries its own settings; the module-level facades use the defaults."""
    d = base("svc-a")
    d["components"] = [component("api", technology="kafka")]
    path = write(tmp_path, d)
    closed = Linter(Settings(vocabulary=Vocabulary(technologies=frozenset({"x"}))))
    assert codes(closed.lint_file(path).issues) == {"E002"}
    assert lint_file(Path(path)).issues == []
