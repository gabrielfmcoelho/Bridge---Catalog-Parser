from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from catalog_parser import lint_cross, lint_file


def component(name="api", **over):
    c = {"name": name, "category": "application", "technology": "rest-api", "protocol": "http",
         "port": 8000, "criticality": "high", "description": "desc"}
    c.update(over)
    return c


def base(ci: str) -> dict:
    return {
        "ci": ci,
        "description": "A system",
        "owners": [{"name": "A", "email": "a@example.org", "username": "a"}],
        "entity": [{"name": "Agency", "slug": "agency", "type": "agency"}],
        "git": {"type": "gitlab", "host": "gitlab.example", "path": f"group/{ci}"},
        "components": [component("api")],
        "dependencies": {"upstream": [], "downstream": []},
    }


def external(ci="oracle-x", **over):
    d = {"ci": ci, "category": "data", "criticality": "medium", "protocol": "tcp",
         "technology": "oracle", "port": 1521, "description": "source"}
    d.update(over)
    return d


def write(root: Path, data: dict) -> Path:
    path = root / data["ci"] / "catalog" / "dependencies.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def pair():
    """svc-a (provider, component api) <- svc-b (consumer, component client): a valid, mirrored link."""
    a, b = base("svc-a"), base("svc-b")
    b["components"] = [component("client")]
    a["dependencies"]["downstream"] = [{"ci": "svc-b", "component": "client", "local_component": "api"}]
    b["dependencies"]["upstream"] = [{"ci": "svc-a", "component": "api", "local_component": "client"}]
    return copy.deepcopy(a), copy.deepcopy(b)


def codes(issues) -> set[str]:
    return {i.code for i in issues}


def lint_one(tmp_path: Path, data: dict):
    return lint_file(write(tmp_path, data))


def lint_all(tmp_path: Path, *docs: dict):
    parsed = [lint_file(write(tmp_path, d)) for d in docs]
    return [i for p in parsed for i in p.issues] + lint_cross(parsed)
