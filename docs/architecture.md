# Arquitetura do Aquiles

## Objetivos

O Aquiles privilegia isolamento de falhas, rastreabilidade e atualização incremental. Fontes externas têm latências e limites distintos; por isso, coleta, modelagem e leitura não compartilham um único processo.

## Camadas

1. **Interface**: componentes Vue consomem contratos HTTP estáveis por meio de `frontend/src/api`.
2. **API**: blueprints Flask validam entrada e convertem resultados de domínio em JSON.
3. **Aplicação**: managers controlam agenda, retomada e estado de cada coletor.
4. **Domínio**: serviços calculam fluxo, risco, fair value, regimes e sinais sem depender da camada visual.
5. **Adaptadores**: clientes OpLab, Bloomberg, WebSocket, CVM, B3 e LLM encapsulam detalhes dos provedores.
6. **Persistência**: portas tipadas isolam PostgreSQL, séries temporais, grafo, arquivos e cache.

Dependências apontam da borda para o domínio. Rotas não devem conter fórmulas financeiras; stores não devem decidir regra de sinal; componentes não devem reconstruir modelos já calculados no backend.

Decisões arquiteturais relevantes são registradas em
[`docs/adr`](adr/README.md). O
[ADR 0001](adr/0001-isolar-fontes-oficiais-funds-flow.md) formaliza o isolamento de
CVM, ANBIMA, B3 e ICI por portas e adaptadores.

## Contextos de negócio

O catálogo executável em `backend/app/domains/catalog.py` define os oito contextos do
backend: `funds_flow`, `options`, `macro`, `market_data`, `graph`, `reports`,
`simulations` e `auth`. Ele é a única fonte para propriedade de blueprints e prefixos
HTTP. Um teste arquitetural exige que cada módulo de API pertença a exatamente um
contexto e impede serviços de importar a camada HTTP.

`funds_flow` é o contexto de referência já migrado. Sua estrutura interna é
`api/`, `application/`, `domain/`, `infrastructure/` e `contracts/`. `api` contém
somente o adaptador Flask; `application` coordena casos de uso e portas; `domain`
mantém regras financeiras puras; `infrastructure`
implementa arquivos e integrações; `contracts` contém os modelos Pydantic de entrada
e saída. Os
demais contextos já possuem a fronteira e a propriedade das rotas, enquanto suas
implementações maiores continuam em `app/api` e `app/services` como adaptadores de
compatibilidade. A migração é vertical e incremental: primeiro contrato, depois caso de
uso e porta, por fim adaptador; endereços HTTP não mudam durante esse processo.

## Processos

O `ecosystem.config.js` é o inventário executável dos processos. Workers de coleta são separados da API principal para que OCR, backfills e WebSockets não bloqueiem requisições. Os wrappers em `scripts/` resolvem o Python do ambiente virtual, propagam sinais e mantêm compatibilidade com PM2 no Windows.

O app factory em `backend/app/__init__.py` cuida somente de HTTP, blueprints,
observabilidade e handlers. Ele não inicia coletores nem importa runtimes de workers.
O ownership operacional fica explícito:

- `aquiles-market-capture`: captura de tela e OCR;
- `aquiles-options-collector-service`: snapshots, OI B3 e coleta de opções;
- `aquiles-options-volume-tracker-service`: polling e backfill de volume;
- `aquiles-collection-scheduler`: CVM/CDA, Funds Flow, fontes de relatório e macro/notícias.

`backend/run_collection_scheduler_service.py` é o único processo que monta os quatro
gerenciadores agendados. Ele escuta apenas em loopback e expõe comandos na porta
`5023`, autenticados por `AQUILES_INTERNAL_SERVICE_TOKEN`.
A API preserva os contratos públicos e encaminha status, start, stop e coleta para
esse serviço. Assim, várias instâncias HTTP não multiplicam loops nem conexões
WebSocket.

### Composição de dependências

`backend/app/container.py` é o ponto central de montagem. No processo HTTP, controles
de coletores são clientes remotos leves. Somente
`AquilesContainer.for_collection_scheduler()` habilita a construção dos gerenciadores
locais. Cada dependência é criada no primeiro uso e uma trava impede duplicação em
acessos concorrentes.

Testes substituem integrações com `override()` no contêiner, sem alterar atributos de
classe ou estado global. O código executável não deve chamar `get_instance()`; um teste
arquitetural percorre a AST do backend e bloqueia a reintrodução desse padrão. Os
entrypoints dedicados usam a mesma composição explícita e não dependem de fachadas
legadas da API.

### Identidade e acesso

`backend/app/auth.py` fornece autenticação compartilhada para o backend principal e
para os serviços dedicados. Tokens assinados carregam a identidade e os papéis do
usuário, expiram no tempo configurado e são revalidados contra o cadastro ativo.
A autorização segue o menor privilégio: GET exige `viewer`, comandos exigem
`operator` e exclusões ou operações administrativas exigem `admin`.

### API de opções

O blueprint público de opções é compartilhado por módulos organizados por caso de uso.
As rotas ficam em `options_routes/`: snapshots e descoberta, modelagem, open interest, mercado,
volatilidade e volume. `options_volume.py` e `options_vol_index.py` preservam seus
imports públicos enquanto são registrados pelo pacote modular.

O mesmo padrão vale para simulações. `simulation_routes/` separa entidades, preparação,
execução, catálogo, atividade e entrevistas. A composição HTTP importa esses pacotes
diretamente. Testes arquiteturais impedem a recriação das fachadas removidas, limitam
os módulos e verificam o inventário de métodos e endereços HTTP.

## Frontend

As rotas principais e os widgets do Discovery usam carregamento assíncrono. Abrir o painel não baixa todos os modelos visuais: cada widget é carregado quando aparece no layout. O registro explícito em `DiscoveryView.vue` mantém os tipos auditáveis e permite ao bundler gerar um artefato independente por widget.

Persistência, grade e ordenação de camadas ficam em `frontend/src/utils/discoveryLayout.js`. Formatação monetária, estados das fontes e cálculos geométricos de curvas ficam em módulos puros dentro de `frontend/src/utils`, cobertos pelo test runner do Node. Componentes Vue coordenam estado e interação; não devem voltar a concentrar essas regras.

Recursos complexos possuem fronteiras próprias em `frontend/src/features`. Funds
Flow e Macro Heatmap são as primeiras migrações e possuem `api/`, `components/` e
`models/`. Componentes importam somente a API da própria feature; clientes Axios,
URLs e detalhes de autenticação ficam fora dos arquivos Vue. Modelos não dependem de
Vue, componentes ou transporte e continuam executáveis diretamente pelo Node.

O gate arquitetural combina regras `no-restricted-imports` do ESLint e testes do
grafo de dependências. Ele bloqueia transporte direto em componentes das features,
modelos acoplados à UI, ciclos de importação e adaptadores concretos importados por
rotas backend. Arquivos em `views/` e nos caminhos legados permanecem como fachadas
curtas enquanto consumidores externos migram para as features.

## Tipagem gradual

Os contratos puros do frontend são verificados com TypeScript em modo `checkJs` e `strict`, mantendo os arquivos JavaScript compatíveis durante a migração. O escopo inicial está em `frontend/tsconfig.typecheck.json` e deve crescer por domínio sempre que um módulo for estabilizado.

No backend, domínios, infraestrutura, composição de dependências, managers de coleta
estabilizados e módulos matemáticos entram no mypy com `strict = true`. O escopo fica
explícito em `backend/pyproject.toml`; adicionar um arquivo ao gate exige corrigir seus
erros, não silenciá-los globalmente. Um teste arquitetural protege a presença desses
grupos no gate. Ruff e ESLint continuam responsáveis por erros estruturais
complementares.

### Funds Flow

`FundsFlowLocalWidget.vue` coordena abas, estado e carregamento. Os estilos ficam em
`FundsFlowLocalWidget.css`, enquanto `cdaGraphOverlay.js` constrói e classifica o
grafo CDA sem depender do ciclo de vida do Vue. No backend,
`funds_flow_local_service.py` orquestra coleta e consolidação,
`funds_flow_utils.py` concentra normalização e cálculos reutilizáveis, e
`funds_flow_insights.py` gera a narrativa determinística do painel. As fronteiras
possuem testes próprios e não alteram os contratos HTTP existentes.

As fontes oficiais são acessadas por portas da camada de aplicação. `CvmSource`,
`AnbimaSource`, `B3Source` e `IciSource` descrevem somente os dados exigidos pelos
casos de uso; os adaptadores concretos ficam em `domains/funds_flow/infrastructure`.
O orquestrador não chama clientes ou rotinas privadas desses provedores diretamente,
permitindo substituir uma fonte pública por uma API licenciada sem alterar rotas,
regras financeiras ou contratos de resposta.

## Contratos operacionais

- toda API deve oferecer `/health` sem acessar redes externas;
- falhas internas recebem `request_id` e mensagem pública estável;
- retries precisam de limite, backoff e timeout explícitos;
- um dado persistido deve carregar fonte e instante de captura;
- jobs idempotentes retomam do último checkpoint confirmado;
- credenciais entram somente por ambiente e nunca em payload de log.

## Dados e persistência

Bases operacionais são estado local, não artefatos de release. O Git contém schemas, código de migração, amostras pequenas e documentação; bases completas permanecem em `backend/uploads` e são reconstruídas pelos coletores.

A responsabilidade de cada meio é explícita:

- **PostgreSQL**: usuários, metadados, estado dos coletores, execuções e resultados estruturados;
- **PostgreSQL particionado ou TimescaleDB**: séries temporais consultadas por ativo e janela;
- **Neo4j**: relacionamentos e projeções de grafo, nunca a fonte oficial dos valores financeiros;
- **arquivos ou object storage**: respostas brutas, planilhas, imagens e relatórios reproduzíveis;
- **Redis**: cache, filas e locks temporários, nunca sistema de registro.

O Funds Flow é a primeira fatia migrada. `application/repositories.py` define as
portas, `infrastructure/json_repositories.py` preserva o modo local e
`infrastructure/postgres_repositories.py` implementa PostgreSQL. O contêiner escolhe
um único backend por meio de `AQUILES_PERSISTENCE_BACKEND`; configuração PostgreSQL
sem `DATABASE_URL` falha na inicialização para impedir gravação dividida.

`backend/migrations/001_persistence_core.sql` cria o schema inicial. A migração deve
ser aplicada antes de habilitar `postgresql`; os arquivos atuais continuam sendo o
padrão de compatibilidade e não são importados automaticamente. Snapshots e estados
passam por modelos Pydantic versionados antes de chegar a qualquer adaptador.

SQLite continua adequado para stores legados de um único host. Esses stores devem
usar WAL, transações curtas, `busy_timeout` e um único owner lógico por base, sendo
migrados por domínio quando precisarem de escrita compartilhada.

## Evolução

Os maiores módulos ainda devem ser divididos por caso de uso, mantendo contratos e testes antes de cada extração. A ordem recomendada é:

1. continuar a extração de DTOs e validação das APIs de opções e macro;
2. separar ingestão, normalização e agregação em CVM/Funds Flow;
3. decompor widgets Vue acima de 1.000 linhas em composables e componentes de visualização;
4. criar testes de contrato para todos os health checks e payloads críticos;
5. mover tarefas assíncronas de modelagem, relatórios e simulações para RQ ou Dramatiq quando houver Redis operacional.
