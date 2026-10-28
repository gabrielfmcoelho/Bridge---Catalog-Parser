"""YAML -> typed model, with line numbers for every finding."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from .issues import ERROR, Issue, format_location
from .models import DependencyCatalog


@dataclass
class Parsed:
    path: Path
    catalog: DependencyCatalog | None = None
    root: yaml.Node | None = None  # composed YAML tree, kept to resolve line numbers
    issues: list[Issue] = field(default_factory=list)

    def line_of(self, loc: tuple) -> int | None:
        return locate(self.root, loc)

    def issue(self, code: str, severity: str, message: str, loc: tuple = (), blame: str = "") -> Issue:
        return Issue(code, severity, message, self.path, self.line_of(loc), format_location(loc), blame)


def locate(root: yaml.Node | None, loc: tuple) -> int | None:
    """Line (1-based) of the node at `loc`; falls back to the deepest node that exists."""
    node = root
    if node is None:
        return None
    for key in loc:
        if isinstance(node, yaml.MappingNode):
            nxt = next((v for k, v in node.value if k.value == key), None)
        elif isinstance(node, yaml.SequenceNode) and isinstance(key, int) and key < len(node.value):
            nxt = node.value[key]
        else:
            nxt = None
        if nxt is None:
            break
        node = nxt
    return node.start_mark.line + 1


def parse_dependencies(path: Path) -> Parsed:
    """Read and validate the shape of a dependencies.yml. Semantic rules are in lint.py."""
    parsed = Parsed(path=path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        parsed.issues.append(Issue("E001", ERROR, f"cannot read file: {e}", path))
        return parsed
    try:
        parsed.root = yaml.compose(text, Loader=yaml.SafeLoader)
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        parsed.issues.append(Issue("E001", ERROR, f"invalid YAML: {getattr(e, 'problem', e)}",
                                   path, mark.line + 1 if mark else None))
        return parsed
    if not isinstance(data, dict):
        parsed.issues.append(Issue("E001", ERROR, "top level must be a mapping", path, 1))
        return parsed
    try:
        parsed.catalog = DependencyCatalog.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            loc = tuple(err["loc"])
            parsed.issues.append(parsed.issue("E002", ERROR, err["msg"], loc))
    return parsed
