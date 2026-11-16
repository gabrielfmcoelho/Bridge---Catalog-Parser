# Contributing to `catalog-parser`

Thank you for your interest in contributing to `catalog-parser`! This guide explains the project's
architecture, extension points, and local development workflow.

## Development Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run pytest -v
```

## Architecture Overview

The library is organized around small, single-responsibility modules under `src/catalog_parser/`:

| Module | Responsibility |
|---|---|
| `config.py` | `Settings`, `Vocabulary`, `SchemaSettings`, `Layout`, `RuleSelection`, `DiagramSettings`, config discovery, `extends` inheritance and `locked` governance |
| `remote.py` | `RemoteConfigLoader`, `RemoteCache`, and `RemoteProvider` implementations (GitLab, GitHub, Bitbucket, generic HTTPS) |
| `dotenv.py` | Reads `CATALOG_PARSER_*` environment variables from `.env` up to the repository boundary (`.git`) |
| `models.py` | Pydantic v2 models (`DependencyCatalog`, `Component`, `Dependency`, `Owner`, `Entity`, `Git`) validated against `Vocabulary` and `SchemaSettings` |
| `parser.py` | `CatalogParser`: parses YAML while keeping the `yaml.Node` AST to map every schema or rule finding to its 1-based line number |
| `rules/` | `FileRule` (single catalog) and `CrossRule` (across catalogs of the same kind), plus the built-in dependency rules (`dependencies.py`) |
| `kinds.py` | `CatalogKind` and `KindRegistry`, mapping filenames (`dependencies.yml`, `owners.yml`, ...) to their model and rules |
| `plugins.py` | Discovers plugins from `importlib.metadata.entry_points(group="catalog_parser.plugins")` and `[rules].plugins` |
| `schema_export.py` | Generates JSON Schemas (`--dump-schema catalog` and `--dump-schema config`) for IDE integration |
| `linter.py` | Orchestrates discovery, parsing, rule execution, rule filtering (`select`/`ignore`) and severity overrides |
| `repository.py` | `Repository`, `PeerLoader` (local paths and remote URLs) and `RepositoryChecker` |
| `diagram.py` | Deterministic Mermaid flowchart and Markdown generator |
| `reporters.py` | Output formatters (`text`, `json`, extensible via `REPORTERS`) |
| `cli.py` | Entry points for `catalog-lint` and `catalog-diagram` |

## Adding a New Rule

1. Subclass `FileRule` (or `ComponentRule` / `EntryRule`) for single-file checks, or `CrossRule` (or `LinkRule`) for multi-repository checks.
2. Assign a unique `RuleInfo(code, severity, summary)`.
3. Yield `Finding(location_tuple, message)` items.
4. Add tests in `tests/test_file_rules.py` or `tests/test_cross_rules.py`.

## Adding a Remote Provider

1. Subclass `RemoteProvider` in `remote.py` and implement `parse(location: str) -> RemoteFile | None`.
2. Register the provider in `PROVIDERS` before `GenericHttpsProvider`.
3. Add URL parsing and relative resolution tests in `tests/test_remote.py` using `FakeFetch` (no real network calls in unit tests).

## Code Style & Guidelines

- **Zero network calls in tests:** Always use `FakeFetch` or the local `ThreadingHTTPServer` fixture.
- **Deterministic outputs:** Diagrams and JSON outputs must never include timestamps or random ordering.
- **Security:** Never include `$CATALOG_PARSER_TOKEN` in exception messages, logs, or cache files, and refuse sending tokens over plain `http://`.
