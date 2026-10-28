# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões seguem [SemVer](https://semver.org/lang/pt-BR/).
Uma tag publicada nunca é movida: correções saem em uma versão nova.

## [Unreleased]

## [0.3.0] - 2026-10-28

O diagrama passa a viver em uma subpasta própria de `docs/`, com um nome que espelha o catálogo.

### Alterado

- **Mudança de caminho (incompatível com a 0.2.0):** o diagrama é gravado em `docs/catalog/dependencies.md`.
  Na 0.2.0 era `docs/catalog-dependencies.md`, solto em `docs/`: o nome agora espelha `catalog/dependencies.yml` e fica dentro de `docs/catalog/`. A subpasta é criada
  quando `docs/` existe; sem `docs/` continua só o aviso `W301`. Novo `--subdir` (parâmetro `subdir` em
  `generate_diagram`); o padrão de `--filename` passa de `catalog-dependencies.md` para `dependencies.md`.
  Quem já gerou o arquivo com a 0.2.0 deve apagar o antigo.

### Instalação

```bash
uv add --dev "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.3.0"
```

## [0.2.0] - 2026-10-28

Diagrama Mermaid dos relacionamentos entre CIs e componentes.

### Adicionado

- **Comando `catalog-diagram [ROOT]`** e `catalog_parser.generate_diagram(root, peers=None, docs_dir="docs", filename="catalog-dependencies.md")`:
  geram `docs/catalog-dependencies.md` com um diagrama Mermaid (`flowchart LR`) do repositório atual — o CI e seus
  componentes em um quadro, os componentes dos CIs vizinhos que ele consome ou serve, e os sistemas externos.
  `A --> B` significa "A depende de B"; o rótulo da aresta é o protocolo/porta de quem fornece (`via X` marca acesso
  indireto); a cor do nó é a criticidade e componentes `data` são cilindros.
- **Pasta `docs/` ausente não falha:** emite o aviso `W301` (stderr, código de saída `0`) e não escreve nada; a pasta
  não é criada. Catálogo ilegível ou com esquema inválido não pode ser desenhado: erros no stderr e código de saída `1`.
- `catalog_parser.render_mermaid(catalog, peers)` devolve só o texto do diagrama.
- Opções do `catalog-diagram`: `--peers PATH` (repetível, ou `$CATALOG_PEERS`) para rotular os componentes que outros
  CIs fornecem; `--docs-dir`, `--filename` e `--stdout` (imprime em vez de gravar, sem exigir `docs/`).
- A saída é determinística (sem data/hora): gerar de novo sem mudar o catálogo não produz diff.

### Alterado

- Internos: `catalog_parser.api` passa a expor `catalog_file`, `repo_root` e `load_peers`, compartilhados com o diagrama.
  `check_repo` mantém o mesmo comportamento.

### Instalação

```bash
uv add --dev "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.2.0"
```

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

[Unreleased]: https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser/releases/tag/v0.1.0
