from __future__ import annotations

from conftest import codes, lint_all, write

from catalog_parser import lint_cross, lint_file


def test_mirrored_link_is_clean(tmp_path, pair):
    assert lint_all(tmp_path, *pair) == []


def test_missing_mirror_is_reported_on_both_sides(tmp_path, pair):
    a, b = pair
    a["dependencies"]["downstream"] = []
    issues = lint_all(tmp_path, a, b)
    assert codes(issues) == {"X003"}
    assert issues[0].path.parts[-3] == "svc-b"


def test_mirror_must_match_both_components(tmp_path, pair):
    a, b = pair
    a["dependencies"]["downstream"][0]["local_component"] = "other"
    a["components"].append({**a["components"][0], "name": "other"})
    assert "X003" in codes(lint_all(tmp_path, a, b))


def test_unknown_component_on_the_other_side(tmp_path, pair):
    a, b = pair
    b["dependencies"]["upstream"][0]["component"] = "ghost"
    assert "X002" in codes(lint_all(tmp_path, a, b))


def test_ci_outside_the_set_is_not_checked_and_warns(tmp_path, pair):
    _, b = pair
    assert codes(lint_all(tmp_path, b)) == {"W203"}


def test_duplicate_ci_across_files(tmp_path, pair):
    a, _ = pair
    first = lint_file(write(tmp_path / "one", a))
    second = lint_file(write(tmp_path / "two", a))
    assert "X001" in codes(lint_cross([first, second]))
