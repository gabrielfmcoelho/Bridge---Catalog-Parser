from __future__ import annotations

import json

from conftest import write

from catalog_parser.cli import main


def test_exit_0_when_clean(tmp_path, pair, capsys):
    for d in pair:
        write(tmp_path, d)
    assert main([str(tmp_path)]) == 0
    assert "0 error(s)" in capsys.readouterr().err


def test_exit_1_and_text_output_on_error(tmp_path, pair, capsys):
    a, b = pair
    a["dependencies"]["downstream"] = []
    write(tmp_path, a), write(tmp_path, b)
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "error X003" in out and "svc-b/catalog/dependencies.yml:" in out


def test_no_cross_skips_x_rules(tmp_path, pair):
    a, b = pair
    a["dependencies"]["downstream"] = []
    write(tmp_path, a), write(tmp_path, b)
    assert main(["--no-cross", str(tmp_path)]) == 0


def test_json_format(tmp_path, pair, capsys):
    a, b = pair
    a["dependencies"]["downstream"] = []
    write(tmp_path, a), write(tmp_path, b)
    main(["--format", "json", str(tmp_path)])
    (item,) = json.loads(capsys.readouterr().out)
    assert item["code"] == "X003" and item["severity"] == "error" and item["line"]


def test_strict_turns_warnings_into_failures(tmp_path, pair):
    a, b = pair
    a["components"][0]["protocol"] = None  # port without protocol -> W201
    a["dependencies"]["downstream"][0]["local_component"] = "api"
    write(tmp_path, a), write(tmp_path, b)
    assert main([str(tmp_path)]) == 0
    assert main(["--strict", str(tmp_path)]) == 1


def test_explicit_file_with_unknown_name_warns(tmp_path, capsys):
    f = tmp_path / "catalog" / "owners.yml"
    f.parent.mkdir()
    f.write_text("a: 1\n")
    assert main([str(f)]) == 0
    assert "W001" in capsys.readouterr().out


def test_missing_path_is_a_usage_error(tmp_path):
    assert main([str(tmp_path / "nope")]) == 2
