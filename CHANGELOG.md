# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).
A published tag is never moved: fixes ship in a new version. Entries up to 0.3.0 are in Portuguese.

## [Unreleased]

## [0.5.0] - 2026-11-16

Deep parametrization and multi-provider remote governance repository support for open-source adoption.

### Added

- **Multi-provider remote configuration & relative resolution (`remote.py`):**
  - Native URL adapters (`RemoteProvider`) for **GitHub** (`/blob/<ref>/<path>` and `api.github.com/repos/.../contents/...`), **Bitbucket** (`/src/<ref>/<path>`), **GitLab** (`/-/blob/` and `/api/v4/`), and generic HTTPS hosts.
  - Custom authentication header support via `$CATALOG_PARSER_AUTH_HEADER`.
  - Relative URL/path resolution (`RemoteFile.resolve_relative`, `resolve_location`) across all providers so remote configs can reference sibling/parent configs and peer catalogs inside the same governance repository.
  - Optional local TTL cache (`RemoteCache`) controlled by `$CATALOG_PARSER_CACHE_TTL` and `$CATALOG_PARSER_CACHE_DIR`.
- **Config inheritance (`extends`) and governance locking (`locked`) (`config.py`):**
  - Config files (local or remote) can inherit from one or more base configs via `extends = "https://..."` or `extends = ["./base.toml"]`, with cycle detection and deep section merging.
  - Base configs can lock sections (`locked = ["vocabulary", "schema"]`) to prevent downstream repositories from overriding organization-wide rules.
- **Configurable `[schema]` policies (`config.py`, `models.py`, `rules/dependencies.py`):**
  - `slug_pattern`: custom regex for `ci`, `component`, `entity.slug`, and `via`.
  - `required_fields`: choose which top-level sections (`owners`, `entity`, `git`, `components`) are mandatory (defaults to `["owners", "entity", "git"]`).
  - `external_required_traits`: customize required inline traits for external `upstream` dependencies (`E104`).
  - `metadata` field on `DependencyCatalog`, `Component`, and `Dependency`, with `required_metadata` validation in `[schema]`.
  - `allow_extra_fields`: optionally permit unknown YAML keys.
- **Extended `[vocabulary]` and `[rules]`:**
  - `vocabulary.entity_types` to govern `entity[].type` values, and `[vocabulary.custom]` for custom rule vocabularies.
  - `[rules.severity]` to override the severity (`error` or `warning`) of any finding code.
  - `[rules].plugins` and `catalog_parser.plugins` entry points (`plugins.py`) to load custom rules, `CatalogKind`s, and `Reporter`s directly from the CLI.
- **Remote peers (`repository.py`, `linter.py`):**
  - `PeerLoader` and `[layout].peers` now accept remote URLs (including relative paths resolved against the remote governance config) in addition to local paths.
- **JSON Schema export (`schema_export.py`, `cli.py`):**
  - `catalog-lint --dump-schema catalog` (reflecting the active vocabulary and schema rules) and `catalog-lint --dump-schema config`.
- **Open-source documentation & tooling:**
  - Added `CONTRIBUTING.md` and `ruff`/`mypy` configuration in `pyproject.toml`.

## [0.4.0] - 2026-11-03

The project becomes generic and open-source: every value that was
specific to one organisation now comes from configuration, and the code is reorganised into small
classes that you extend without editing the library.

### Added

- **Configuration** in `.catalog-parser.toml`, in `[tool.catalog-parser]` of `pyproject.toml`, or in
  the file named by `$CATALOG_PARSER_CONFIG`. It is searched from the repository upwards to the
  first folder with `.git`. Sections:
  `[vocabulary]` (technologies, protocols, git providers, categories, data categories, criticalities),
  `[layout]` (catalog folder, peers env var, skipped folders), `[rules]` (`select`/`ignore` by code
  or prefix) and `[diagram]` (paths, direction, title, legend, colours per criticality).
  An unknown key is a configuration error (exit code `2`).
- **Config from a URL**, so the rules can live in a central repository that nobody clones:
  `--config URL` or `CATALOG_PARSER_CONFIG=URL`, with the token in `$CATALOG_PARSER_TOKEN`.
  A GitLab file page (`/-/blob/<ref>/<path>`) is translated into the files API call and sent with
  `PRIVATE-TOKEN`; other URLs get `Authorization: Bearer`. The token is never sent over plain http
  and never printed. A failed download is a configuration error (exit code `2`), never a fallback.
  This uses only the standard library, so there is no new dependency.
- **`.env` support:** `CATALOG_PARSER_CONFIG` and `CATALOG_PARSER_TOKEN` can live in a `.env`
  file instead of being exported. The file is searched from the linted repository up to its
  `.git`. Only `CATALOG_PARSER_*` keys are read, and the shell environment wins over the file.
  `.env.example` documents the keys.
- CLI: `--config FILE|URL` on both commands; `catalog-lint --select/--ignore CODES` and `--list-rules`.
- Extension points: `FileRule`/`CrossRule` (one class per code), `CatalogKind` + `KindRegistry`,
  `Reporter` + `REPORTERS`, and the services `Linter`, `RepositoryChecker`, `DiagramGenerator`,
  `MermaidRenderer` and `CatalogDiscoverer`, all exported from `catalog_parser`.
- `examples/` with two repositories that link to each other, a shared config, and the generated diagram.
- `py.typed`, package metadata (URLs, classifiers), and a GitHub Actions test workflow.
