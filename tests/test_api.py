from __future__ import annotations

import pytest
from conftest import codes, write

from catalog_parser import check_repo
from catalog_parser.testing import assert_catalog_valid


@pytest.fixture
def broken(pair):
    """svc-b declares the link, svc-a (provider) forgot the mirror."""
    a, b = pair
    a["dependencies"]["downstream"] = []
    return a, b


def test_clean_repo_with_peer(tmp_path, pair):
    a, b = pair
    fa, _ = write(tmp_path, a), write(tmp_path, b)
    assert check_repo(fa.parents[1], peers=[tmp_path]) == []


def test_without_peers_the_link_is_unchecked_and_says_so(tmp_path, pair):
    _, b = pair
    fb = write(tmp_path, b)
    assert codes(check_repo(fb.parents[1], peers=[])) == {"W203"}


def test_declaring_side_gets_the_error(tmp_path, broken):
    a, b = broken
    write(tmp_path, a); fb = write(tmp_path, b)
    issues = check_repo(fb.parents[1], peers=[tmp_path])
    assert codes(issues) == {"X003"} and issues[0].path == fb


def test_missing_side_also_gets_the_error(tmp_path, broken):
    """The omission is in svc-a: linting svc-a with its peers must fail, not just svc-b."""
    a, b = broken
    fa = write(tmp_path, a); write(tmp_path, b)
    issues = check_repo(fa.parents[1], peers=[tmp_path])
    assert codes(issues) == {"X003"} and issues[0].blame == "svc-a"


def test_peer_problems_unrelated_to_this_repo_are_not_reported(tmp_path, pair):
    a, b = pair
    b["components"].append(dict(b["components"][0]))  # E101 in the peer (still loads, so the link is checked)
    fa = write(tmp_path, a); write(tmp_path, b)
    assert check_repo(fa.parents[1], peers=[tmp_path]) == []


def test_peers_from_environment(tmp_path, broken, monkeypatch):
    a, b = broken
    fa = write(tmp_path, a); write(tmp_path, b)
    monkeypatch.setenv("CATALOG_PEERS", str(tmp_path))
    assert codes(check_repo(fa.parents[1])) == {"X003"}


def test_assert_helper(tmp_path, broken):
    a, b = broken
    fa = write(tmp_path, a); write(tmp_path, b)
    with pytest.raises(AssertionError, match="X003"):
        assert_catalog_valid(fa.parents[1], peers=[tmp_path])
    fb = tmp_path / "svc-b"
    assert_catalog_valid(fb, peers=[])           # W203 is only a warning...
    with pytest.raises(AssertionError, match="W203"):
        assert_catalog_valid(fb, peers=[], strict=True)  # ...unless strict
