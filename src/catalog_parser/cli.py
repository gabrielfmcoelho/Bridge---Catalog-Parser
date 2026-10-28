"""catalog-lint [PATH ...] — lint catalog/*.yml files, one by one and across repositories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .issues import ERROR, WARNING, Issue
from .kinds import CROSS_LINTERS, FILE_LINTERS, discover


def run(paths: list[Path], cross: bool = True) -> list[Issue]:
    issues: list[Issue] = []
    by_kind: dict[str, list] = {}
    for f in discover(paths):
        linter = FILE_LINTERS.get(f.name)
        if linter is None:
            issues.append(Issue("W001", WARNING, f"no schema registered for '{f.name}'", f))
            continue
        parsed = linter(f)
        issues.extend(parsed.issues)
        by_kind.setdefault(f.name, []).append(parsed)
    if cross:
        for kind, files in by_kind.items():
            issues.extend(CROSS_LINTERS[kind](files))
    return sorted(issues, key=lambda i: (str(i.path), i.line or 0, i.code))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="catalog-lint", description=__doc__)
    ap.add_argument("paths", nargs="*", type=Path, default=[Path(".")],
                    help="files, or directories searched for catalog/<kind> (default: .)")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--no-cross", action="store_true", help="skip the cross-file rules (X###)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args(argv)

    missing = [p for p in args.paths if not p.exists()]
    if missing:
        print(f"catalog-lint: no such path: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2

    issues = run(args.paths, cross=not args.no_cross)
    if args.format == "json":
        print(json.dumps([i.to_dict() for i in issues], indent=2, ensure_ascii=False))
    else:
        for i in issues:
            print(i.format())
        errors = sum(i.severity == ERROR for i in issues)
        print(f"{errors} error(s), {len(issues) - errors} warning(s)", file=sys.stderr)
    failing = {ERROR, WARNING} if args.strict else {ERROR}
    return 1 if any(i.severity in failing for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
