"""`CATALOG_PARSER_*` variables from a `.env` file, so the config URL and token need no `export`.

The `.env` is the nearest one from the starting folder up to the repository boundary (a folder with
`.git`), the same search as the config file. Only keys starting with `CATALOG_PARSER_` are read,
so a repository can keep its other variables in the same file. Variables already set in the
environment win over the file. `.env` holds credentials: keep it in `.gitignore`.

Format: `KEY=value` per line; blank lines, `# comments` and an `export ` prefix are allowed; a
value may be wrapped in single or double quotes; an unquoted value ends at ` #`. No interpolation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

DOTENV_FILE = ".env"
PREFIX = "CATALOG_PARSER_"


def find_dotenv(start: str | Path = ".") -> Path | None:
    here = Path(start).resolve()
    if not here.is_dir():
        here = here.parent
    for folder in (here, *here.parents):
        candidate = folder / DOTENV_FILE
        if candidate.is_file():
            return candidate
        if (folder / ".git").exists():
            return None
    return None


def _value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw.split(" #", 1)[0].strip()


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, raw = line.partition("=")
        key = key.strip()
        if sep and key:
            values[key] = _value(raw)
    return values


def catalog_env(start: str | Path = ".", environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The `CATALOG_PARSER_*` variables: the `.env` found from `start`, overridden by `environ`."""
    environ = os.environ if environ is None else environ
    found = find_dotenv(start)
    values = {}
    if found:
        try:
            values = {k: v for k, v in parse_dotenv(found.read_text(encoding="utf-8")).items() if k.startswith(PREFIX)}
        except (OSError, UnicodeDecodeError):
            values = {}
    values.update({k: v for k, v in environ.items() if k.startswith(PREFIX)})
    return values
