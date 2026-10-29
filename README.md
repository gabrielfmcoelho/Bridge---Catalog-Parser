# catalog-parser

A linter and diagram generator for **dependency catalogs**: one small YAML file per repository
(`catalog/dependencies.yml`) that says what the system is made of and which other systems it
talks to, in each direction.

- **Lint** each catalog (schema, references, duplicates) with errors that point at the right line.
- **Cross-check** catalogs across repositories: if A says it consumes B, B must list A as a consumer.
- **Draw** a Mermaid map of each repository into `docs/`. GitHub, GitLab and VS Code render it.
- **Use it in tests**: one assertion in a repository's own test suite keeps its catalog honest.

Every project-specific choice is configurable, and new rules, catalog kinds and output formats plug in
without editing the library. The configurable choices are the allowed technologies, protocols and
criticalities, the folder layout, which rules run, and how the diagram looks.

## Install

```bash
pip install "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.4.0"
# or, as a dev dependency with uv
uv add --dev "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.4.0"
```

Requires Python 3.11+.

## The catalog

```yaml
# <repo>/catalog/dependencies.yml
ci: shop-api                         # this system (a "configuration item"), usually the repository name
description: Orders and payments API
owners:   [{ name: Jane Doe, email: jane@example.org, username: jdoe }]
entity:   [{ name: Example Corp, slug: example-corp, type: company }]
git:      { type: github, host: github.com, path: example-corp/shop-api }

components:                          # the parts of THIS system; traits live here
  - { name: api, category: application, technology: rest-api, protocol: https, port: 8443,
      criticality: high, description: Public REST API }

dependencies:
  upstream:                          # what this system consumes
    - ci: payment-gateway            # external system (no catalog): traits inline
      local_component: api
      category: service
      technology: rest-api
      protocol: https
      port: 443
      criticality: high
      description: Card payments
  downstream:                        # who consumes this system
    - { ci: shop-web, component: frontend, local_component: api }   # another catalogued system
    - { ci: bi-dashboard, local_component: api }                    # consumer without a catalog
```

- `ci` + `component` identify the **other** end of a link; `local_component` is **this** system's end.
- A link between two catalogued systems must be declared on both sides (the *mirror*): `shop-api`
  lists `shop-web` downstream, and `shop-web` lists `shop-api` upstream.
- External systems have no `component`, so they carry their traits inline.

A complete two-repository example, with its generated diagram, is in [`examples/`](examples/).

## Command line

```bash
catalog-lint                                   # every catalog under the current folder
catalog-lint ../repo-a ../repo-b               # several repositories: mirrors are checked between them
catalog-lint path/to/catalog/dependencies.yml  # one file
catalog-lint --format json .                   # machine-readable output
catalog-lint --ignore E110 --select E,X .      # choose rules (codes or prefixes)
catalog-lint --list-rules                      # every code with its meaning
catalog-diagram .                              # writes docs/catalog/dependencies.md
catalog-diagram . --peers ..                   # also label the components other repositories provide
catalog-diagram . --stdout                     # print instead of writing
```

`catalog-lint` exits with `0` when there are no errors, `1` on errors (or on warnings with
`--strict`), and `2` on a usage or configuration error. `--no-cross` turns off the cross-file rules
(`X###`).

The behaviour of `catalog-diagram`:
- The file is written to `<docs_dir>/<subdir>/<filename>`, which is `docs/catalog/dependencies.md`
  by default. The subfolder is created when the docs folder exists.
- **No docs folder:** you get warning `W301` on stderr and exit code `0`, and nothing is created.
- **Invalid catalog:** there is nothing to draw, so the errors go to stderr and the exit code is `1`.
- The output has no timestamps, so regenerating it without catalog changes produces no diff.
- In the diagram, `A --> B` means *A depends on B*. The edge label is the provider's protocol and
  port. The colour is the criticality, and cylinders are data components.

## Configuration

Settings are read from the first of these that applies:

1. `--config FILE|URL` (CLI) or `settings=` (Python);
2. `$CATALOG_PARSER_CONFIG`, a path or a URL (see [Central rules from a URL](#central-rules-from-a-url));
3. the nearest `.catalog-parser.toml`, or `pyproject.toml` with a `[tool.catalog-parser]` table,
   searching from the repository (from the working directory for `catalog-lint`) upwards, up to and
   including the first folder that contains `.git`;
4. the built-in defaults below.

Every key is optional. Unknown keys are errors.

```toml
# .catalog-parser.toml  (in pyproject.toml, prefix each table with "tool.catalog-parser.")

[vocabulary]
# Omit a list to accept any value; set it to make the list closed (other values -> E002).
technologies  = ["postgresql", "redis", "rest-api"]   # default: any
protocols     = ["http", "https", "tcp", "grpc"]      # default: any
git_providers = ["github", "gitlab"]                  # default: any
categories    = ["service", "data", "infrastructure", "application"]  # default shown
data_categories = ["data"]              # stored data: no protocol/port (W202), drawn as cylinders
criticalities = ["high", "medium", "low"]               # ordered, most critical first

[layout]
catalog_dir = "catalog"                 # relative to the repository root; may be nested (".meta/catalog")
peers_env   = "CATALOG_PEERS"           # env var with os.pathsep-separated peers
skip_dirs   = [".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build", "target"]

[rules]
select = []                             # codes or prefixes; empty = all
ignore = ["E110"]                       # e.g. git.path need not end with the ci name

[diagram]
docs_dir  = "docs"
subdir    = "catalog"
filename  = "dependencies.md"
direction = "LR"                        # LR, RL, TB, TD, BT
title     = "Dependency map — {ci}"
legend    = "..."                       # markdown under the diagram

[diagram.styles]                        # criticality -> Mermaid classDef (no entry = no colour)
high   = "fill:#f8d7da,stroke:#c0392b,color:#000"
medium = "fill:#fff3cd,stroke:#b7950b,color:#000"
low    = "fill:#d4edda,stroke:#1e8449,color:#000"
```

### Central rules from a URL

If every repository defines its own vocabulary, whoever writes a catalog also decides what is valid
in it. To avoid that, keep the config in **one central repository** and read it over HTTPS.
Nobody has to clone that repository:

```bash
export CATALOG_PARSER_CONFIG="https://gitlab.example.org/platform/catalog-governance/-/blob/main/.catalog-parser.toml"
export CATALOG_PARSER_TOKEN="glpat-..."   # only for private projects
catalog-lint .                            # or --config <URL>; the pytest helper reads the env var too
```

How each kind of URL is read:
- **GitLab file page** (`/-/blob/<ref>/<path>` or `/-/raw/...`, as copied from the browser): it
  is translated into the files API call and sent with `PRIVATE-TOKEN`. The token needs the
  `read_api` scope and at least Reporter access to the project.
- **GitLab API URL** (`.../api/v4/...`): used as-is, also with `PRIVATE-TOKEN`.
- **Any other URL:** used as-is, with `Authorization: Bearer <token>`.

The token is never sent over plain `http://` and never appears in error messages. If the download
fails, the run stops with exit code `2`, and you get a hint for 401/403/404. It never falls back to
other settings.

Use a tag as the ref (e.g. `/-/blob/v1/...`) to pin a version of the rules. An explicit config,
whether a URL or a path, replaces any `.catalog-parser.toml` inside the linted repository; the two
are never merged.

## Rules

| Code | Severity | What it checks |
|---|---|---|
| E001 | error | unreadable file, invalid YAML, or top level is not a mapping |
| E002 | error | schema: type, allowed value (vocabulary), unknown field, missing required field |
| E101 | error | duplicate component name |
| E102 | error | `local_component` not declared in this file |
| E103 | error | inline traits on an entry with `component` (traits live on the component) |
| E104 | error | external `upstream` without `category`/`technology`/`criticality`/`description` |
| E105 | error | `downstream` entry without `component` carrying traits |
| E106 | error | entry with `component` but no `local_component` |
| E107 | error | `downstream` entry without `local_component` |
| E108 | error | CI depending on itself |
| E109 | error | duplicate entry in the same list |
| E110 | error | `git.path` does not end with the `ci` name |
| E112 | error | `via` points at this same CI |
| W001 | warning | file name with no registered catalog kind |
| W201 | warning | component with `port` but no `protocol` |
| W202 | warning | data component with `protocol`/`port` |
| W203 | warning | CI referenced with `component` whose catalog was not loaded: link not checked |
| W301 | warning | docs folder not found: diagram not written |
| X001 | error | same `ci` declared in two files |
| X002 | error | `component` not declared by the referenced CI |
| X003 | error | link without its mirror on the other side; `blame` names the CI that must add it |

`X002` and `X003` only apply between catalogs loaded in the same run. A reference with `component` to a
CI whose catalog was not loaded gives `W203`. External systems, which have no `component`, never do.

## In a repository's test suite

```python
# tests/test_catalog.py
from catalog_parser.testing import assert_catalog_valid

def test_catalog_valid():
    assert_catalog_valid(".")                     # this repository only: links become W203
    # assert_catalog_valid(".", peers=["../other-repo"], strict=True)   # also check the mirrors
```

`peers` (or `$CATALOG_PEERS`) loads other repositories' catalogs as context. Their own problems
are not reported. The exception is a peer that points at this CI with no mirror here (X003): the
omission is in this repository, so this repository fails.

## As a library

```python
from pathlib import Path
from catalog_parser import Linter, RepositoryChecker, Settings, DiagramGenerator

settings = Settings.discover(".")                 # or Settings.from_file(...), or Settings(...)
linter = Linter(settings)
issues = linter.lint_paths([Path("../repo-a"), Path("../repo-b")])
issues = RepositoryChecker(linter).check(".", peers=[".."])
result = DiagramGenerator(linter).generate(".", write=False)   # result.markdown
```

The functions from earlier versions are still available and use the default settings, or the
discovered ones for repository-level calls. They are `lint_file`, `lint_cross`, `check_repo`,
`generate_diagram`, `render_mermaid` and `parse_dependencies`.

## Extending

Each extension point is a small class, so you add new behaviour without editing the library.

**A rule:** subclass `FileRule` (one catalog) or `CrossRule` (all catalogs of a kind). Each rule owns
one code.

```python
from catalog_parser import DEPENDENCIES, CatalogKind, FileRule, Finding, KindRegistry, Linter
from catalog_parser.issues import WARNING, RuleInfo

class NeedsDescriptionLength(FileRule):
    info = RuleInfo("C001", WARNING, "component description shorter than 10 characters")

    def check(self, catalog, vocabulary):
        for i, c in enumerate(catalog.components):
            if len(c.description) < 10:
                yield Finding(("components", i, "description"), f"describe '{c.name}' better")

kind = CatalogKind(DEPENDENCIES.filename, DEPENDENCIES.model,
                   (*DEPENDENCIES.file_rules, NeedsDescriptionLength()), DEPENDENCIES.cross_rules)
linter = Linter(registry=KindRegistry([kind]))
```

**A catalog kind** (e.g. `catalog/owners.yml`): write a pydantic model and its rules, then
`registry.register(CatalogKind("owners.yml", OwnersModel, file_rules=(...)))`. Discovery, line
numbers, rule selection and the CLI work unchanged. Pass the registry to `cli.main(argv, registry=...)`
to build your own command.

**An output format:** subclass `Reporter` and add it to `catalog_parser.REPORTERS`. Its key becomes
a `--format` choice.

## In CI

GitHub Actions:

```yaml
- uses: astral-sh/setup-uv@v6
- run: uvx --from "git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.4.0" catalog-lint .
```

GitLab CI:

```yaml
catalog-lint:
  image: ghcr.io/astral-sh/uv:python3.12-bookworm-slim
  script:
    - uvx --from "git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.4.0" catalog-lint .
```

## Development

```bash
uv sync          # library + dev dependencies
uv run pytest
```

Code map: `config.py` (settings), `remote.py` (config over HTTPS), `models.py` (schema), `parser.py` (YAML with line numbers),
`rules/` (one class per code), `kinds.py` (catalog kinds), `discovery.py`, `linter.py`,
`repository.py` (one repository and its peers), `diagram.py`, `reporters.py` and `cli.py`.

## License

MIT. See [LICENSE](LICENSE).
