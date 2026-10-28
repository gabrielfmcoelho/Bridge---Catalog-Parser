from __future__ import annotations

from conftest import base, codes, component, external, lint_one


def test_valid_catalog_has_no_issues(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [external()]
    assert lint_one(tmp_path, d).issues == []


def test_invalid_yaml_reports_line(tmp_path):
    path = tmp_path / "svc-a" / "catalog" / "dependencies.yml"
    path.parent.mkdir(parents=True)
    path.write_text("ci: svc-a\nowners: [unclosed\n", encoding="utf-8")
    from catalog_parser import lint_file
    (issue,) = lint_file(path).issues
    assert issue.code == "E001" and issue.line is not None


def test_top_level_must_be_mapping(tmp_path):
    path = tmp_path / "svc-a" / "catalog" / "dependencies.yml"
    path.parent.mkdir(parents=True)
    path.write_text("- a\n- b\n", encoding="utf-8")
    from catalog_parser import lint_file
    assert codes(lint_file(path).issues) == {"E001"}


def test_schema_errors_point_at_the_line(tmp_path):
    d = base("svc-a")
    d["components"][0]["criticality"] = "urgent"
    d["components"][0]["extra"] = 1
    parsed = lint_one(tmp_path, d)
    assert codes(parsed.issues) == {"E002"}
    assert {i.location for i in parsed.issues} == {"components[0].criticality", "components[0].extra"}
    assert all(i.line for i in parsed.issues)


def test_semantic_rules_do_not_run_on_a_broken_schema(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api"), component("api"), component("bad", port=0)]
    assert codes(lint_one(tmp_path, d).issues) == {"E002"}


def test_duplicate_component(tmp_path):
    d = base("svc-a")
    d["components"].append(component("api"))
    assert "E101" in codes(lint_one(tmp_path, d).issues)


def test_local_component_must_exist(tmp_path):
    d = base("svc-a")
    d["dependencies"]["downstream"] = [{"ci": "svc-b", "component": "x", "local_component": "ghost"}]
    assert "E102" in codes(lint_one(tmp_path, d).issues)


def test_traits_not_allowed_next_to_component(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [{"ci": "svc-b", "component": "x", "local_component": "api", "port": 80}]
    assert "E103" in codes(lint_one(tmp_path, d).issues)


def test_external_needs_traits(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [{"ci": "oracle-x"}]
    (issue,) = [i for i in lint_one(tmp_path, d).issues if i.code == "E104"]
    assert "category" in issue.message and "description" in issue.message


def test_downstream_without_component_cannot_carry_traits(tmp_path):
    d = base("svc-a")
    d["dependencies"]["downstream"] = [{"ci": "dashboard", "local_component": "api", "criticality": "high"}]
    assert "E105" in codes(lint_one(tmp_path, d).issues)


def test_downstream_consumer_without_a_catalog_is_fine(tmp_path):
    d = base("svc-a")
    d["dependencies"]["downstream"] = [{"ci": "dashboard", "local_component": "api"}]
    assert lint_one(tmp_path, d).issues == []


def test_component_requires_local_component(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [{"ci": "svc-b", "component": "x"}]
    assert "E106" in codes(lint_one(tmp_path, d).issues)


def test_downstream_requires_local_component(tmp_path):
    d = base("svc-a")
    d["dependencies"]["downstream"] = [{"ci": "dashboard"}]
    assert "E107" in codes(lint_one(tmp_path, d).issues)


def test_self_dependency_and_self_via(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [external(ci="svc-a"), external(via="svc-a")]
    assert {"E108", "E112"} <= codes(lint_one(tmp_path, d).issues)


def test_duplicate_entry(tmp_path):
    d = base("svc-a")
    d["dependencies"]["upstream"] = [external(), external()]
    assert "E109" in codes(lint_one(tmp_path, d).issues)


def test_git_path_must_end_with_ci(tmp_path):
    d = base("svc-a")
    d["git"]["path"] = "group/other-name"
    assert "E110" in codes(lint_one(tmp_path, d).issues)


def test_warnings(tmp_path):
    d = base("svc-a")
    d["components"] = [component("api", protocol=None), component("tbl", category="data", technology="iceberg")]
    d["components"][1]["port"] = 1
    codes_found = codes(lint_one(tmp_path, d).issues)
    assert {"W201", "W202"} <= codes_found
