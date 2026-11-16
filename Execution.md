# Guia de Execução — `catalog-parser`

Este documento apresenta um passo a passo didático para **instalar**, **configurar** e **executar** o `catalog-parser` (tanto na validação de catálogos com `catalog-lint` quanto na geração de diagramas com `catalog-diagram`).

---

## 1. Pré-requisitos

- **Python 3.11** ou superior (`python3 --version`)
- Gerenciador de pacotes **[uv](https://docs.astral.sh/uv/)** (recomendado) ou `pip`

```mermaid
flowchart LR
  Install["1. Instalar Pacote"] --> CreateCatalog["2. Criar catalog/dependencies.yml"]
  CreateCatalog --> Config["3. Configurar Regras (Local ou Remota)"]
  Config --> Lint["4. Validar com catalog-lint"]
  Lint --> Diagram["5. Gerar Diagrama com catalog-diagram"]
```

---

## 2. Como Instalar

Escolha o cenário que melhor se adapta ao seu uso:

### Cenário A: Instalar em um projeto existente (como dependência de desenvolvimento)
Se você está em um repositório de microsserviço, API ou pipeline de dados e quer validar o catálogo desse projeto:

```bash
# Usando uv (recomendado)
uv add --dev "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.5.0"

# Ou usando pip
pip install "catalog-parser @ git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.5.0"
```

### Cenário B: Executar diretamente sem instalar no projeto (`uvx`)
Com o `uvx`, você pode rodar o linter ou o gerador de diagramas imediatamente em qualquer pasta:

```bash
uvx --from "git+https://github.com/gabrielfmcoelho/Bridge---Catalog-Parser@v0.5.0" catalog-lint .
```

### Cenário C: Clonar este repositório para desenvolvimento local
Se você clonou o repositório do próprio `catalog-parser` na sua máquina:

```bash
cd catalog-parser
uv sync
```
> **Dica:** No Cenário C, prefixe os comandos abaixo com `uv run` (por exemplo, `uv run catalog-lint ...`) para executá-los dentro do ambiente virtual gerenciado pelo `uv`.

---

## 3. Criando o Arquivo de Catálogo

Por padrão, o `catalog-parser` procura o arquivo `catalog/dependencies.yml` na raiz de cada repositório.

1. Crie a pasta `catalog/` na raiz do seu repositório:
   ```bash
   mkdir -p catalog
   ```
2. Crie o arquivo `catalog/dependencies.yml` seguindo o exemplo comentado abaixo:

```yaml
# catalog/dependencies.yml
ci: shop-api                         # Identificador único do sistema (geralmente o nome do repositório)
description: API de pedidos e pagamentos

owners:                              # Responsáveis técnicos pelo sistema
  - name: Jane Doe
    email: jane@example.org
    username: jdoe

entity:                              # Organização, diretoria ou squad dona do sistema
  - name: Example Corp
    slug: example-corp
    type: company

git:                                 # Onde o código vive (`path` deve terminar com o nome do `ci`)
  type: github
  host: github.com
  path: example-corp/shop-api

components:                          # Componentes internos que fazem parte DESTE sistema
  - name: api
    category: application
    technology: rest-api
    protocol: https
    port: 8443
    criticality: high
    description: API REST pública
  - name: orders-db
    category: data                   # Componentes 'data' não levam porta/protocolo e viram cilindros no diagrama
    technology: postgresql
    criticality: high
    description: Banco de dados relacional de pedidos

dependencies:
  upstream:                          # O que ESTE sistema consome
    # Caso 1: Sistema externo (não possui catálogo próprio -> atributos declarados inline)
    - ci: payment-gateway
      local_component: api           # Qual componente local faz a chamada
      category: service
      technology: rest-api
      protocol: https
      port: 443
      criticality: high
      description: Gateway externo de cartões

  downstream:                        # Quem consome ESTE sistema
    # Caso 2: Outro sistema catalogado (informa `component` do outro lado + `local_component` daqui)
    - ci: shop-web
      component: frontend
      local_component: api
    # Caso 3: Consumidor sem catálogo próprio (omite `component`)
    - ci: bi-dashboard
      local_component: api
```

---

## 4. Executando o Linter (`catalog-lint`)

O comando `catalog-lint` verifica a sintaxe YAML, o schema dos campos, o vocabulário permitido e a consistência das referências.

### 4.1. Validar o repositório atual
```bash
catalog-lint .
```
- **Saída esperada quando tudo está válido:**
  ```text
  0 error(s), 0 warning(s)
  ```
- **Códigos de retorno (Exit Codes):**
  - `0`: Nenhum erro encontrado.
  - `1`: Erros de catálogo encontrados (ou avisos, se usado `--strict`).
  - `2`: Erro de uso ou de configuração (arquivo inexistente, TOML inválido, falha ao baixar config remota).

### 4.2. Validar múltiplos repositórios juntos (Checagem Cruzada `X001`–`X003`)
Quando você passa dois ou mais repositórios (ou uma pasta pai que contém vários repositórios), o `catalog-lint` confere se os vínculos entre sistemas catalogados estão **espelhados nos dois lados**:

```bash
# Testando com os repositórios de exemplo incluídos no projeto:
catalog-lint examples/shop-api examples/shop-web
# ou apontando para a pasta que contém ambos:
catalog-lint examples/
```

### 4.3. Opções úteis do `catalog-lint`

```bash
# Listar todas as regras existentes e seus códigos
catalog-lint --list-rules

# Ignorar regras específicas (ex.: ignorar E110 que exige git.path terminando com o ci)
catalog-lint --ignore E110 .

# Executar apenas uma família de regras (ex.: apenas erros de arquivo E1xx)
catalog-lint --select E1 .

# Pular regras cruzadas entre repositórios (X001, X002, X003)
catalog-lint --no-cross .

# Tratar avisos (warnings W###) como erro (retorna exit code 1)
catalog-lint --strict .

# Saída em formato JSON (ideal para integração com outras ferramentas)
catalog-lint --format json .
```

---

## 5. Configurando Regras Locais ou via Repositório Remoto

Você pode parametrizar vocabulários fechados, obrigatoriedade de campos, severidade de regras e estilo do diagrama usando um arquivo `.catalog-parser.toml` (ou a tabela `[tool.catalog-parser]` no `pyproject.toml`).

### 5.1. Usando um Repositório Remoto de Configurações (Governança Centralizada)

Para não haver confusão sobre onde cada arquivo fica, considere que existem **3 repositórios distintos**:

| Repositório | Papel | O que fica nele? |
|---|---|---|
| **1. `catalog-parser`** *(a ferramenta)* | Biblioteca/CLI open source instalada via `uv` ou `pip` | Apenas o código do parser (você **não** edita nada nele). |
| **2. Repositório Remoto de Governança** *(ex.: `sua-org/catalog-governance`)* | Repositório central da sua empresa/organização | O arquivo `.catalog-parser.toml` mestre com o vocabulário e regras oficiais da organização. |
| **3. Repositório Avaliado pelo Linter** *(ex.: `sua-org/shop-api`)* | O sistema/serviço que você quer validar | O catálogo `catalog/dependencies.yml` + o `.catalog-parser.toml` (ou `.env`) apontando para o repositório de governança. |

```mermaid
flowchart TB
  subgraph GovRepo["2. Repositório Remoto de Governança (sua-org/catalog-governance)"]
    MasterCfg[".catalog-parser.toml (regras e vocabulário da empresa)"]
  end

  subgraph TargetRepo["3. Repositório Avaliado pelo Linter (sua-org/shop-api)"]
    LocalCatalog["catalog/dependencies.yml"]
    LocalToml[".catalog-parser.toml (extends = URL remota)"]
    LocalEnv[".env (CATALOG_PARSER_TOKEN)"]
  end

  LocalToml -->|"herda via HTTPS"| MasterCfg
```

#### Opção 1: Herança via `extends` no `.catalog-parser.toml` (Recomendado)
Crie um `.catalog-parser.toml` na raiz do **repositório que você quer avaliar com o linter** (ex.: `shop-api/.catalog-parser.toml`), herdando da URL do **repositório remoto de governança**:

```toml
# <repositório-avaliado>/.catalog-parser.toml
extends = "https://github.com/sua-org/catalog-governance/blob/v1/.catalog-parser.toml"

# Você pode customizar seções não bloqueadas para este repositório específico:
[diagram]
docs_dir = "docs"
direction = "LR"
```

Se o repositório remoto de governança for **privado**, defina o token no arquivo `.env` na raiz do **repositório avaliado** (ou como variável de ambiente no seu terminal):

```bash
# <repositório-avaliado>/.env
CATALOG_PARSER_TOKEN=ghp_seu_token_aqui
# Opcional: cache local em segundos para não baixar a configuração a cada execução
CATALOG_PARSER_CACHE_TTL=300
```

#### Opção 2: Apontar diretamente via `.env` ou `--config`
Se não quiser criar um `.catalog-parser.toml` no **repositório avaliado**, você pode definir a URL diretamente no `.env` dele:

```bash
# <repositório-avaliado>/.env
CATALOG_PARSER_CONFIG=https://gitlab.example.org/platform/governance/-/blob/main/.catalog-parser.toml
CATALOG_PARSER_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
```
Ou passar a URL explicitamente ao rodar o comando sobre o repositório avaliado:
```bash
catalog-lint --config https://github.com/sua-org/governance/blob/main/.catalog-parser.toml /caminho/do/repositorio-avaliado
```

### 5.2. Exemplo completo de `.catalog-parser.toml` (para o Repositório de Governança)

```toml
# Impede que repositórios filhos alterem o vocabulário ou o schema obrigatório
locked = ["vocabulary", "schema"]

[vocabulary]
technologies  = ["postgresql", "redis", "rest-api", "celery", "react"]
protocols     = ["http", "https", "tcp", "grpc"]
git_providers = ["github", "gitlab"]
entity_types  = ["company", "directorate", "squad"]

[schema]
slug_pattern             = "^[a-z0-9][a-z0-9-]*$"
required_fields          = ["owners", "entity", "git"]   # remova "entity" se não quiser exigi-lo
external_required_traits = ["category", "technology", "criticality", "description"]
required_metadata        = []                            # ex.: ["domain", "tier"]

[layout]
catalog_dir = "catalog"
# Opcional: URLs ou caminhos de catálogos vizinhos para validar X002/X003 sem clonar repositórios
peers       = []

[rules]
ignore  = []
plugins = []

[rules.severity]
# Exemplo: transformar aviso de link não verificado (W203) em erro ou E110 em warning
# W203 = "error"
# E110 = "warning"
```

---

## 6. Gerando Diagramas Mermaid (`catalog-diagram`)

O comando `catalog-diagram` lê o `catalog/dependencies.yml` do repositório e gera uma página Markdown com um fluxograma Mermaid determinístico.

### 6.1. Visualizar o diagrama no terminal (`--stdout`)
Não exige que a pasta `docs/` exista:

```bash
catalog-diagram examples/shop-api --peers examples/shop-web --stdout
```

### 6.2. Gravar o diagrama em `docs/catalog/dependencies.md`
Por segurança, o `catalog-diagram` só grava o arquivo se a pasta `docs/` (ou a pasta configurada em `diagram.docs_dir`) **já existir** no repositório. Caso contrário, ele emite o aviso `W301` e não cria pastas soltas.

```bash
# 1. Garanta que a pasta docs/ existe no repositório alvo
mkdir -p docs

# 2. Gere o arquivo docs/catalog/dependencies.md
catalog-diagram .

# 3. Ou informe repositórios vizinhos (--peers) para exibir o protocolo e porta dos componentes remotos
catalog-diagram examples/shop-api --peers examples/shop-web
```

---

## 7. Autocomplete na IDE (JSON Schema) e Uso com `pytest`

### 7.1. Exportar JSON Schema para VS Code / IDEs
Você pode gerar o JSON Schema do catálogo já adaptado ao vocabulário da sua organização:

```bash
# Gera o JSON Schema de dependencies.yml com os enums da configuração ativa
catalog-lint --dump-schema catalog > catalog.schema.json

# Gera o JSON Schema para validar arquivos .catalog-parser.toml
catalog-lint --dump-schema config > catalog-parser-config.schema.json
```

No topo do seu `catalog/dependencies.yml`, adicione o comentário da extensão YAML (RedHat YAML no VS Code):
```yaml
# yaml-language-server: $schema=../catalog.schema.json
ci: shop-api
```

### 7.2. Validar o catálogo dentro da suíte de testes (`pytest`) do seu projeto
Adicione um teste em `tests/test_catalog.py` no repositório do seu serviço para garantir que o catálogo nunca quebre:

```python
from catalog_parser.testing import assert_catalog_valid


def test_catalog_is_valid():
    # Lê automaticamente o .catalog-parser.toml ou .env do repositório
    assert_catalog_valid(".")
```

Para executar:
```bash
pytest
```
