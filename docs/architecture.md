# Arquitetura do Aquiles

## Objetivos

O Aquiles privilegia isolamento de falhas, rastreabilidade e atualização incremental. Fontes externas têm latências e limites distintos; por isso, coleta, modelagem e leitura não compartilham um único processo.

## Camadas

1. **Interface**: componentes Vue consomem contratos HTTP estáveis por meio de `frontend/src/api`.
2. **API**: blueprints Flask validam entrada e convertem resultados de domínio em JSON.
3. **Aplicação**: managers controlam agenda, retomada e estado de cada coletor.
4. **Domínio**: serviços calculam fluxo, risco, fair value, regimes e sinais sem depender da camada visual.
5. **Adaptadores**: clientes OpLab, Bloomberg, WebSocket, CVM, B3 e LLM encapsulam detalhes dos provedores.
6. **Persistência**: stores controlam SQLite/JSONL, retenção, índices e leitura concorrente.

Dependências apontam da borda para o domínio. Rotas não devem conter fórmulas financeiras; stores não devem decidir regra de sinal; componentes não devem reconstruir modelos já calculados no backend.

## Processos

O `ecosystem.config.js` é o inventário executável dos processos. Workers de coleta são separados da API principal para que OCR, backfills e WebSockets não bloqueiem requisições. Os wrappers em `scripts/` resolvem o Python do ambiente virtual, propagam sinais e mantêm compatibilidade com PM2 no Windows.

O app factory em `backend/app/__init__.py` cuida somente de HTTP, blueprints, observabilidade e handlers. A retomada dos coletores está isolada em `backend/app/startup.py` e pode ser desativada em testes com `AQUILES_START_BACKGROUND_SERVICES=False`.

### Identidade e acesso

`backend/app/auth.py` fornece autenticação compartilhada para o backend principal e
para os serviços dedicados. Tokens assinados carregam a identidade e os papéis do
usuário, expiram no tempo configurado e são revalidados contra o cadastro ativo.
A autorização segue o menor privilégio: GET exige `viewer`, comandos exigem
`operator` e exclusões ou operações administrativas exigem `admin`.

### API de opções

O blueprint público de opções é compartilhado por módulos organizados por caso de uso.
`backend/app/api/options.py` mantém consultas e comandos gerais,
`options_volume.py` concentra atividade, hedge e controle do tracker, e
`options_vol_index.py` possui cache, sincronização e endpoints do índice de
volatilidade. Essa divisão preserva os endereços HTTP enquanto impede que estado e
regras de subsistemas independentes voltem a se acumular no arquivo principal.

## Frontend

As rotas principais e os widgets do Discovery usam carregamento assíncrono. Abrir o painel não baixa todos os modelos visuais: cada widget é carregado quando aparece no layout. O registro explícito em `DiscoveryView.vue` mantém os tipos auditáveis e permite ao bundler gerar um artefato independente por widget.

Persistência, grade e ordenação de camadas ficam em `frontend/src/utils/discoveryLayout.js`. Formatação monetária, estados das fontes e cálculos geométricos de curvas ficam em módulos puros dentro de `frontend/src/utils`, cobertos pelo test runner do Node. Componentes Vue coordenam estado e interação; não devem voltar a concentrar essas regras.

### Funds Flow

`FundsFlowLocalWidget.vue` coordena abas, estado e carregamento. Os estilos ficam em
`FundsFlowLocalWidget.css`, enquanto `cdaGraphOverlay.js` constrói e classifica o
grafo CDA sem depender do ciclo de vida do Vue. No backend,
`funds_flow_local_service.py` orquestra coleta e consolidação,
`funds_flow_utils.py` concentra normalização e cálculos reutilizáveis, e
`funds_flow_insights.py` gera a narrativa determinística do painel. As fronteiras
possuem testes próprios e não alteram os contratos HTTP existentes.

## Contratos operacionais

- toda API deve oferecer `/health` sem acessar redes externas;
- falhas internas recebem `request_id` e mensagem pública estável;
- retries precisam de limite, backoff e timeout explícitos;
- um dado persistido deve carregar fonte e instante de captura;
- jobs idempotentes retomam do último checkpoint confirmado;
- credenciais entram somente por ambiente e nunca em payload de log.

## Dados

Bases operacionais são estado local, não artefatos de release. O Git contém schemas, código de migração, amostras pequenas e documentação; bases completas permanecem em `backend/uploads` e são reconstruídas pelos coletores.

SQLite é adequado para os stores locais de um único host. Serviços com escrita frequente devem usar WAL, transações curtas, `busy_timeout` e um único owner lógico por base. A migração para PostgreSQL passa a ser indicada quando houver múltiplos hosts escrevendo no mesmo domínio.

## Evolução

Os maiores módulos ainda devem ser divididos por caso de uso, mantendo contratos e testes antes de cada extração. A ordem recomendada é:

1. continuar a extração de DTOs e validação das APIs de opções e macro;
2. separar ingestão, normalização e agregação em CVM/Funds Flow;
3. decompor widgets Vue acima de 1.000 linhas em composables e componentes de visualização;
4. criar testes de contrato para todos os health checks e payloads críticos;
5. substituir estado global de managers por injeção explícita onde a concorrência exigir.
