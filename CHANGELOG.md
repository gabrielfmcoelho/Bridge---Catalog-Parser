# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).
Uma tag publicada nunca é movida: correções saem em uma versão nova.

## [Unreleased]

## [0.1.0] - 2026-10-28

Primeira versão: parser e linter para `catalog/dependencies.yml`.

### Adicionado

- **Modelo e parser** (pydantic v2): CI, componentes (`category`, `technology`, `protocol`, `port`,
  `criticality`, `description`) e dependências `upstream`/`downstream` identificadas por `ci` + `component`
  da outra ponta e `local_component` deste CI. Sistemas externos levam as características inline.
  Todo achado traz a linha do arquivo.
- **Regras por arquivo:** `E001`–`E002` (YAML e esquema), `E101`–`E110` e `E112` (componentes, referências,
  duplicidades, `git.path`), `W201`–`W202` (porta sem protocolo, componente de dados com protocolo/porta).
- **Regras entre arquivos:** `X001` (`ci` duplicado), `X002` (componente inexistente no CI referenciado),
  `X003` (vínculo sem espelho; o campo `blame` indica o CI que precisa acrescentar a entrada) e
  `W203` (vínculo não conferido porque o catálogo do outro CI não foi carregado).
- **API para repositórios consumidores:** `catalog_parser.check_repo(root, peers=None)` e o helper de pytest
  `catalog_parser.testing.assert_catalog_valid(root, peers=None, strict=False)`. Os `peers` (ou a variável
  `CATALOG_PEERS`) servem de contexto: problemas próprios deles não são reportados, mas um peer que aponta
  para este CI sem espelho aqui é.
- **CLI `catalog-lint`:** aceita arquivos ou pastas (procura `catalog/dependencies.yml`), `--format text|json`,
  `--no-cross` e `--strict`. Código de saída `0` sem erros, `1` com erros (ou avisos em `--strict`), `2` uso incorreto.
- **Registro de tipos de catálogo** (`kinds.py`): novos arquivos de `catalog/` entram sem mudar descoberta nem CLI.
- Licença MIT.

### Limitações conhecidas

- Só `dependencies.yml` tem esquema; outros arquivos de `catalog/` passados explicitamente geram `W001`.
- A CLI reporta os problemas de **todos** os arquivos recebidos; o filtro por repositório (`peers`) existe
  apenas na API Python e no helper de pytest.
- `X002`/`X003` só valem entre catálogos carregados na mesma execução.

### Instalação

```bash
uv add --dev "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.1.0"
```

[Unreleased]: https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser/releases/tag/v0.1.0
