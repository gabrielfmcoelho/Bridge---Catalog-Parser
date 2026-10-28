# catalog-parser

Parser e linter dos arquivos `catalog/*.yml` dos repositórios de um data lakehouse.
Hoje cobre `catalog/dependencies.yml` (catálogo de dependências entre CIs e componentes).

## Uso

```bash
uv sync                                   # instala a lib e as dependências de dev
uv run catalog-lint ../repo-a ../repo-b                              # varre catalog/dependencies.yml
uv run catalog-lint caminho/catalog/dependencies.yml                  # um arquivo
uv run catalog-lint --format json .       # saída para ferramentas
uv run pytest                             # testes
```

Códigos de saída: `0` sem erros · `1` erros (ou avisos com `--strict`) · `2` uso incorreto.
`--no-cross` desliga as regras entre arquivos (`X###`).

Como biblioteca:

```python
from catalog_parser import lint_file, lint_cross

parsed = [lint_file(p) for p in paths]           # Parsed: .catalog (modelo pydantic), .issues
issues = [i for p in parsed for i in p.issues] + lint_cross(parsed)
```

## Regras

| Código | Severidade | O que verifica |
|---|---|---|
| E001 | erro | arquivo ilegível / YAML inválido / raiz não é um mapa |
| E002 | erro | esquema: tipo, enum, campo desconhecido, obrigatório ausente |
| E101 | erro | componente duplicado |
| E102 | erro | `local_component` não declarado neste arquivo |
| E103 | erro | características inline em entrada que tem `component` (elas vivem no componente) |
| E104 | erro | externo em `upstream` sem `category`/`technology`/`criticality`/`description` |
| E105 | erro | `downstream` sem `component` carregando características |
| E106 | erro | entrada com `component` sem `local_component` |
| E107 | erro | `downstream` sem `local_component` |
| E108 | erro | CI dependendo de si mesmo |
| E109 | erro | entrada duplicada na mesma lista |
| E110 | erro | `git.path` não termina com o nome do `ci` |
| E112 | erro | `via` aponta para o próprio CI |
| W201 | aviso | componente com `port` sem `protocol` |
| W202 | aviso | componente `data` com `protocol`/`port` |
| X001 | erro | mesmo `ci` em dois arquivos |
| X002 | erro | `component` não declarado no CI referenciado |
| X003 | erro | vínculo sem o espelho do outro lado (`ci` + `component` + `local_component`); `blame` = o CI que precisa acrescentar a entrada |
| W203 | aviso | CI referenciado com `component` cujo catálogo não foi carregado: vínculo não conferido |

`X002`/`X003` só valem entre os catálogos carregados na mesma execução; uma referência com `component` a um CI
cujo catálogo não foi carregado gera `W203` (o vínculo não foi conferido). Sistemas externos, que não têm
`component`, não geram aviso.

## Como dependência de um repositório

A lib é pensada para ser **dependência de dev** de cada repositório e rodar na suíte de testes dele.

```toml
# pyproject.toml do repo (uv)
[dependency-groups]
dev = ["catalog-parser"]

[tool.uv.sources]
catalog-parser = { git = "https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser", tag = "v0.1.0" }
```

Com `requirements-dev.txt`: `catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.1.0`

```python
# tests/test_catalog.py
from catalog_parser.testing import assert_catalog_valid

def test_catalog_valid():
    assert_catalog_valid(".")                       # só este repo: E/W; vínculos viram W203
    # assert_catalog_valid(".", peers=["../outro-repo"], strict=True)   # com vizinhos, confere o espelho
```

`peers` (ou a variável `CATALOG_PEERS`, separada por `:`) carrega os catálogos dos outros repositórios como
contexto. Problemas **deles** não são reportados aqui, exceto um peer que aponta para este CI sem espelho
(X003): a omissão é deste repositório, então é ele que falha. Também vale na linha de comando:
`uv run catalog-lint .`.

## Modelo (resumo)

- **CI**: o sistema (um repositório). **Component**: peça interna do CI; é onde vivem
  `category`, `technology`, `protocol`, `port`, `criticality` e `description`.
- Em `dependencies.upstream|downstream`, `ci` + `component` identificam a **outra ponta**;
  `local_component` é o componente **deste** CI no vínculo.
- Sistemas externos (sem catálogo) levam as características inline.

## Adicionar um novo tipo de catálogo

1. Modelos em `src/catalog_parser/models.py` (ou módulo novo) e regras no mesmo molde de `lint.py`.
2. Registrar o nome do arquivo em `src/catalog_parser/kinds.py` (`FILE_LINTERS`, e `CROSS_LINTERS` se houver regras entre arquivos).
3. Testes em `tests/`.

## No CI de um repositório (GitLab)

```yaml
catalog-lint:
  image: ghcr.io/astral-sh/uv:python3.12-bookworm-slim   # ou a imagem padrão do projeto
  script:
    - uvx --from git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.1.0 catalog-lint catalog/dependencies.yml
```

## Licença

MIT — veja [LICENSE](LICENSE).
