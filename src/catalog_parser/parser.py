"""YAML -> typed model, with line numbers for every finding."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from .config import Settings, Vocabulary
from .issues import ERROR, Issue, RuleInfo, format_location
from .models import DEFAULT_VOCABULARY, DependencyCatalog

UNREADABLE = RuleInfo("E001", ERROR, "unreadable file, invalid YAML, or top level is not a mapping")
SCHEMA = RuleInfo("E002", ERROR, "schema: type, allowed value, unknown field, missing required field")


@dataclass
class Parsed:
    path: Path
    catalog: BaseModel | None = None  # e.g. a DependencyCatalog; None when the file could not be loaded
    root: yaml.Node | None = None     # composed YAML tree, kept to resolve line numbers
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


class CatalogParser:
    """Reads one YAML file into `model` and validates its shape. Semantic rules run later (Linter)."""

    def __init__(self, model: type[BaseModel], vocabulary: Vocabulary = DEFAULT_VOCABULARY):
        self.model = model
        self.vocabulary = vocabulary

    def parse(self, path: Path) -> Parsed:
        parsed = Parsed(path=path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            parsed.issues.append(Issue(UNREADABLE.code, ERROR, f"cannot read file: {e}", path))
            return parsed
        try:
            parsed.root = yaml.compose(text, Loader=yaml.SafeLoader)
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            parsed.issues.append(Issue(UNREADABLE.code, ERROR, f"invalid YAML: {getattr(e, 'problem', e)}",
                                       path, mark.line + 1 if mark else None))
            return parsed
        if not isinstance(data, dict):
            parsed.issues.append(Issue(UNREADABLE.code, ERROR, "top level must be a mapping", path, 1))
            return parsed
        try:
            parsed.catalog = self.model.model_validate(data, context={"vocabulary": self.vocabulary})
        except ValidationError as e:
            for err in e.errors():
                parsed.issues.append(parsed.issue(SCHEMA.code, ERROR, err["msg"], tuple(err["loc"])))
        return parsed


def parse_dependencies(path: Path, settings: Settings | None = None) -> Parsed:
    """Read and validate the shape of a dependencies catalog. Semantic rules are in rules/."""
    vocabulary = settings.vocabulary if settings else DEFAULT_VOCABULARY
    return CatalogParser(DependencyCatalog, vocabulary).parse(Path(path))
