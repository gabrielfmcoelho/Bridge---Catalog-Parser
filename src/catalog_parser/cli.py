"""catalog-lint [PATH ...] — lint catalog files, one by one and across repositories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, Settings
from .diagram import NO_DOCS, DiagramGenerator
from .issues import ERROR, WARNING
from .kinds import KindRegistry, default_registry
from .linter import UNKNOWN_KIND, Linter
from .parser import SCHEMA, UNREADABLE
from .reporters import REPORTERS

CORE_RULES = (UNREADABLE, SCHEMA, UNKNOWN_KIND, NO_DOCS)


def _codes(values: list[str] | None) -> frozenset[str] | None:
    """`--select E1,W2 --select X` -> {"E1", "W2", "X"}; None when the option was not given."""
    if values is None:
        return None
    return frozenset(c.strip() for v in values for c in v.split(",") if c.strip())


def _settings(config: str | None, start: Path) -> Settings:
    return Settings.load(config) if config else Settings.discover(start)


def _add_config(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--config", metavar="FILE|URL",
                    help="config file (.catalog-parser.toml or pyproject.toml) or URL, e.g. a GitLab file page "
                         "(token in $CATALOG_PARSER_TOKEN); default: $CATALOG_PARSER_CONFIG, else the nearest one found")


def list_rules(registry: KindRegistry) -> None:
    for info in sorted([*CORE_RULES, *(r.info for r in registry.rules())], key=lambda i: i.code):
        print(f"{info.code}  {info.severity:<7}  {info.summary}")


def main(argv: list[str] | None = None, registry: KindRegistry | None = None) -> int:
    registry = registry or default_registry()
    ap = argparse.ArgumentParser(prog="catalog-lint", description=__doc__)
    ap.add_argument("paths", nargs="*", type=Path, default=[Path(".")],
                    help="files, or directories searched for <catalog_dir>/<kind> (default: .)")
    ap.add_argument("--format", choices=tuple(REPORTERS), default="text")
    ap.add_argument("--no-cross", action="store_true", help="skip the cross-file rules (X###)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--select", action="append", metavar="CODES",
                    help="only these codes or prefixes, comma-separated (replaces the configured selection)")
    ap.add_argument("--ignore", action="append", metavar="CODES",
                    help="skip these codes or prefixes, comma-separated (added to the configured ones)")
    ap.add_argument("--list-rules", action="store_true", help="print every finding code and exit")
    _add_config(ap)
    args = ap.parse_args(argv)

    if args.list_rules:
        list_rules(registry)
        return 0
    missing = [p for p in args.paths if not p.exists()]
    if missing:
        print(f"catalog-lint: no such path: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2
    try:
        settings = _settings(args.config, Path.cwd()).with_rules(_codes(args.select), _codes(args.ignore) or frozenset())
    except ConfigError as e:
        print(f"catalog-lint: {e}", file=sys.stderr)
        return 2

    issues = Linter(settings, registry).lint_paths(args.paths, cross=not args.no_cross)
    REPORTERS[args.format]().emit(issues)
    failing = {ERROR, WARNING} if args.strict else {ERROR}
    return 1 if any(i.severity in failing for i in issues) else 0


def diagram_main(argv: list[str] | None = None) -> int:
    """catalog-diagram [ROOT] — write the Mermaid dependency map to <ROOT>/<docs_dir>/<subdir>/."""
    ap = argparse.ArgumentParser(prog="catalog-diagram", description=diagram_main.__doc__)
    ap.add_argument("root", nargs="?", type=Path, default=Path("."), help="repository folder (default: .)")
    ap.add_argument("--peers", action="append", type=Path, default=None, metavar="PATH",
                    help="repository or catalog of another CI, to label the components it provides; "
                         "repeatable (default: the env var named by layout.peers_env, $CATALOG_PEERS)")
    ap.add_argument("--docs-dir", help="folder under ROOT (default: diagram.docs_dir, docs)")
    ap.add_argument("--subdir", help="folder under the docs folder (default: diagram.subdir, catalog)")
    ap.add_argument("--filename", help="file name (default: diagram.filename, dependencies.md)")
    ap.add_argument("--stdout", action="store_true", help="print the markdown instead of writing a file")
    _add_config(ap)
    args = ap.parse_args(argv)

    if not args.root.exists():
        print(f"catalog-diagram: no such path: {args.root}", file=sys.stderr)
        return 2
    try:
        settings = _settings(args.config, args.root).with_diagram(
            docs_dir=args.docs_dir, subdir=args.subdir, filename=args.filename)
    except ConfigError as e:
        print(f"catalog-diagram: {e}", file=sys.stderr)
        return 2
    result = DiagramGenerator(Linter(settings)).generate(args.root, args.peers, write=not args.stdout)
    for issue in result.issues:
        print(issue.format(), file=sys.stderr)
    if result.markdown is None:  # catalog unreadable or schema-invalid: nothing to draw
        return 1
    if args.stdout:
        print(result.markdown, end="")
    elif result.path:
        print(f"wrote {result.path}")
    return 0  # a missing docs folder is only a warning


if __name__ == "__main__":
    sys.exit(main())
