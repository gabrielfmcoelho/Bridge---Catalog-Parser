# catalog-parser

A linter and diagram generator for **dependency catalogs**: one small YAML file per repository
(`catalog/dependencies.yml`) that says what the system is made of and which other systems it
talks to, in each direction.

- **Lint** each catalog (schema, references, duplicates) with errors that point at the right line.
- **Cross-check** catalogs across repositories (local or remote): if A says it consumes B, B must list A as a consumer.
- **Draw** a Mermaid map of each repository into `docs/`. GitHub, GitLab and VS Code render it.
- **Govern centrally**: keep your organization's vocabulary, schema requirements, rule severities, and peer catalogs in a **remote configuration repository** (GitHub, GitLab, Bitbucket, or HTTPS).
- **Use it in tests**: one assertion in a repository's own test suite keeps its catalog honest.

Every project-specific choice is configurable, and new rules, catalog kinds and output formats plug in
without editing the library.

## Install

```bash
pip install "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.5.0"
# or, as a dev dependency with uv
uv add --dev "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.5.0"
```

Requires Python 3.11+.

## Instructions on how to execute

### 1. Point to your rules (once per repository)

Add the two variables to the `.env` of each repository that has a catalog, and keep `.env` in its
`.gitignore`, because the file holds a token. [`.env.example`](.env.example) lists the keys.

```bash
# <repo>/.env
CATALOG_PARSER_CONFIG=https://gitlab.example.org/platform/catalog-governance/-/blob/main/.catalog-parser.toml
CATALOG_PARSER_TOKEN=glpat-...            # read_api scope; only for private projects
```

`CATALOG_PARSER_CONFIG` can also be a local path. See [Central rules from a URL](#central-rules-from-a-url)
for how the URL and the token are used.

### 2. Run

Without installing anything (`uvx` downloads and runs it):

```bash
cd my-repo
uvx --from "git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.4.0" catalog-lint --no-cross .
```

Or install it once as a global tool:

```bash
uv tool install "git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.4.0"
cd my-repo
catalog-lint --no-cross .
```

**One repository:** use `--no-cross` when the other repositories are not next to it. Without it,
every link to a catalog that was not loaded becomes a `W203` warning.

**All repositories at once:** run from the folder that holds them side by side. This also runs
the cross-repository rules (`X001`–`X003`, such as a missing mirror):

```bash
cd workspace                              # contains repo-a/, repo-b/, ...
catalog-lint repo-a repo-b repo-c
```

Here the `.env` search starts in `workspace/`, not inside each repository, so that folder needs its
own `.env` with the same two lines. If `workspace/` is itself a Git repository, ignore `.env` there too.

**The diagram** is a separate command: `catalog-diagram . --peers ..` writes
`docs/catalog/dependencies.md`.

Useful options:

| Option | Use it to |
|---|---|
| `--no-cross` | lint one repository alone |
| `--strict` | fail (exit `1`) on warnings too |
| `--format json` | get machine-readable output |
| `--select E1` / `--ignore E110` | choose rules by code or prefix |
| `--list-rules` | list every code and its meaning |
| `--config FILE\|URL` | override the `.env` for one run, e.g. to try the rules of another branch |

Exit codes: `0` no errors · `1` errors (or warnings with `--strict`) · `2` usage, configuration or
access error (token, URL).

### What happens when the variables are missing

| Situation | Result |
|---|---|
| No `CATALOG_PARSER_CONFIG` anywhere (shell, `.env`, `--config`) and no local config file | The built-in [defaults](#configuration) are used: `technology`, `protocol` and `git.type` accept **any** value, while the structural rules still run. **Nothing tells you this happened**, so check the `.env` before trusting a clean result. |
| `CATALOG_PARSER_TOKEN` without `CATALOG_PARSER_CONFIG` | The token is ignored; it is only used to download a remote config. |
| `CATALOG_PARSER_CONFIG` is a URL to a private project, and the token is missing or wrong | The server answers 401/403/404 and the run stops with exit code `2` and a hint. It never falls back to the defaults. |

### If the project pins catalog-parser

In a repository that has catalog-parser as a dev dependency, `uv run catalog-lint` runs the
**pinned** version. Versions before 0.4.0 read neither `.env` nor a config URL, so use `uvx` or
`uv tool` as above, or bump the pin.

## The catalog

```yaml
# <repo>/catalog/dependencies.yml
ci: shop-api                         # this system (a "configuration item"), usually the repository name
description: Orders and payments API
owners:   [{ name: Jane Doe, email: jane@example.org, username: jdoe }]
entity:   [{ name: Example Corp, slug: example-corp, type: company }]
git:      { type: github, host: github.com, path: example-corp/shop-api }
metadata: { domain: commerce, tier: tier-1 }   # optional custom metadata (governable via [schema])

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
catalog-lint --dump-schema catalog             # JSON Schema for dependencies.yml (tailored to active config)
catalog-lint --dump-schema config              # JSON Schema for .catalog-parser.toml
catalog-diagram .                              # writes docs/catalog/dependencies.md
catalog-diagram . --peers ..                   # also label the components other repositories provide
catalog-diagram . --stdout                     # print instead of writing
```

`catalog-lint` exits with `0` when there are no errors, `1` on errors (or on warnings with
`--strict`), and `2` on a usage or configuration error. `--no-cross` turns off the cross-file rules
(`X###`).

## Configuration

Settings are read from the first of these that applies:

1. `--config FILE|URL` (CLI) or `settings=` (Python);
2. `$CATALOG_PARSER_CONFIG`, a path or a URL, from the environment or a `.env` file;
3. the nearest `.catalog-parser.toml`, or `pyproject.toml` with a `[tool.catalog-parser]` table,
   searching from the repository (from the working directory for `catalog-lint`) upwards, up to and
   including the first folder that contains `.git`;
4. the built-in defaults below.

Every key is optional. Unknown keys are errors.

```toml
# .catalog-parser.toml  (in pyproject.toml, prefix each table with "tool.catalog-parser.")
extends = "https://github.com/my-org/catalog-governance/blob/v1/base.toml"
locked  = ["vocabulary", "schema"]      # prevent child configs from overriding these sections

[vocabulary]
# Omit a list to accept any value; set it to make the list closed (other values -> E002).
technologies    = ["postgresql", "redis", "rest-api"]   # default: any
protocols       = ["http", "https", "tcp", "grpc"]      # default: any
git_providers   = ["github", "gitlab"]                  # default: any
entity_types    = ["company", "directorate", "squad"]   # default: any
categories      = ["service", "data", "infrastructure", "application"]  # default shown
data_categories = ["data"]              # stored data: no protocol/port (W202), drawn as cylinders
criticalities   = ["high", "medium", "low"]             # ordered, most critical first

[vocabulary.custom]                     # arbitrary custom vocabularies for plugins/custom rules
tier = ["tier-1", "tier-2", "tier-3"]

[schema]
slug_pattern             = "^[a-z0-9][a-z0-9-]*$"       # regex for ci, component, entity.slug, via
required_fields          = ["owners", "entity", "git"]  # omit "entity" or "git" to make them optional
external_required_traits = ["category", "technology", "criticality", "description"]
required_metadata        = []                           # e.g. ["domain", "tier"]
allow_extra_fields       = false                        # true = ignore unknown YAML keys

[layout]
catalog_dir = "catalog"                 # relative to the repository root; may be nested (".meta/catalog")
peers_env   = "CATALOG_PEERS"           # env var with os.pathsep-separated peers
skip_dirs   = [".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build", "target"]
peers       = []                        # local paths or remote URLs (resolved relative to this config)

[rules]
select  = []                            # codes or prefixes; empty = all
ignore  = ["E110"]                      # e.g. git.path need not end with the ci name
plugins = []                            # e.g. ["my_org_rules:register"]

[rules.severity]                        # promote warnings to errors or demote errors to warnings
W203 = "error"
E110 = "warning"

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

### Remote Configuration Repository & Inheritance (`extends` + `locked`)

To govern rules centrally across many repositories without duplicating configuration:

1. **Create a central governance repository** holding your base `.catalog-parser.toml` (with `locked = ["vocabulary", "schema"]`), optional team profiles (`extends = "../.catalog-parser.toml"`), and even remote peer catalogs (`[layout] peers = ["./peers/shop-api.yml"]`).
2. **In each service repository**, either:
   - Commit a 1-line `.catalog-parser.toml` with `extends = "https://github.com/org/governance/blob/v1/.catalog-parser.toml"` (and customize unlocked sections like `[diagram]`), or
   - Point `CATALOG_PARSER_CONFIG` to the remote URL in `.env` or environment variables.

Supported URL formats out of the box:
- **GitHub file page** (`/blob/<ref>/<path>` or `/raw/...`) and **GitHub Contents API** (`/repos/<owner>/<repo>/contents/<path>`): authenticated with `Authorization: Bearer <token>`.
- **GitLab file page** (`/-/blob/<ref>/<path>` or `/-/raw/...`) and **GitLab API** (`.../api/v4/...`): translated into the Repository Files API and authenticated with `PRIVATE-TOKEN`.
- **Bitbucket file page** (`/src/<ref>/<path>`): translated into the Bitbucket 2.0 source API with `Authorization: Bearer <token>`.
- **Any other HTTPS URL:** fetched as-is with `Authorization: Bearer <token>` (or `$CATALOG_PARSER_AUTH_HEADER`).

Set `CATALOG_PARSER_CACHE_TTL=300` (in seconds) in `.env` or the shell environment to cache remote
configs and remote peer catalogs locally.

## Rules

| Code | Default Severity | What it checks |
|---|---|---|
| E001 | error | unreadable file, invalid YAML, or top level is not a mapping |
| E002 | error | schema: type, allowed value (vocabulary), unknown field, missing required field/metadata |
| E101 | error | duplicate component name |
| E102 | error | `local_component` not declared in this file |
| E103 | error | inline traits on an entry with `component` (traits live on the component) |
| E104 | error | external `upstream` missing traits listed in `schema.external_required_traits` |
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

## IDE Autocomplete (JSON Schema)

Generate a JSON Schema that includes your organization's active `[vocabulary]` and `[schema]` rules:

```bash
catalog-lint --dump-schema catalog > catalog.schema.json
catalog-lint --dump-schema config > catalog-parser-config.schema.json
```

## Extending & Plugins

In addition to using the Python API (`FileRule`, `CrossRule`, `CatalogKind`, `Reporter`), you can
register plugins via `[rules] plugins = ["my_pkg.rules:register"]` in `.catalog-parser.toml` or via
Python package entry points (`[project.entry-points."catalog_parser.plugins"]`). See
[CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT. See [LICENSE](LICENSE).
