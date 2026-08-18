# CVM CDA Graph Architecture

Projeto: Funds Flow Local  
Fonte: CVM CDA Carteiras  
Microservico: aquiles-cvm-cda-graph-service  
Porta padrao: 5017  
Banco operacional de origem: `backend/uploads/macro/cvm_cda/cvm_cda.sqlite`  
Banco de grafo: Neo4j local  

## Objetivo

Transformar a base CVM CDA em um grafo deterministico de carteiras de fundos brasileiros.

O CDA e o equivalente brasileiro mais proximo do N-PORT, mas a semantica principal nao deve ser inferida por LLM. Os nos e arestas sao criados a partir de linhas estruturadas:

- fundo
- ativo
- emissor
- classe de ativo
- pais
- tipo de fundo
- competencia mensal
- temas analiticos como exterior, credito privado, derivativos e confidencial

Graphiti/OpenAI continuam relevantes para memoria narrativa, explicacao e enriquecimento textual posterior. O grafo CDA nasce deterministico para manter rastreabilidade e evitar alucinacao sobre posicoes.

## Arquivos

```text
backend/app/services/cvm_cda_graph_service.py
backend/run_cvm_cda_graph_service.py
scripts/run-cvm-cda-graph-service.js
frontend/src/api/cdaGraph.js
```

## Runtime

```text
GET  http://localhost:5017/health
GET  http://localhost:5017/api/v1/cda-graph/status
GET  http://localhost:5017/api/v1/cda-graph/schema
POST http://localhost:5017/api/v1/cda-graph/build
GET  http://localhost:5017/api/v1/cda-graph/network
GET  http://localhost:5017/api/v1/cda-graph/fund/{cnpj}/network
GET  http://localhost:5017/api/v1/cda-graph/crowding/issuers
```

O processo tambem foi incluido no `ecosystem.config.js` como:

```text
aquiles-cvm-cda-graph-service
```

## Schema

### Nos

```text
CdaMonth
CdaFund
CdaFundType
CdaAsset
CdaIssuer
CdaAssetClass
CdaCountry
CdaExposureTarget
```

### Relacionamentos

```text
(CdaFund)-[:REPORTED_IN]->(CdaMonth)
(CdaFund)-[:HAS_FUND_TYPE]->(CdaFundType)
(CdaFund)-[:HOLDS_POSITION]->(CdaAsset)
(CdaAsset)-[:ISSUED_BY]->(CdaIssuer)
(CdaAsset)-[:CLASSIFIED_AS]->(CdaAssetClass)
(CdaAsset)-[:LOCATED_IN]->(CdaCountry)
(CdaFund)-[:HAS_TARGET_EXPOSURE]->(CdaExposureTarget)
```

## Metricas nas arestas

`HOLDS_POSITION`:

```text
value_market
abs_value_market
pct_pl
side
qty_final
value_cost
value_buy
value_sell
source_block
asset_class
asset_subclass
is_foreign
is_confidential
is_related_issuer
position_rank
```

`HAS_TARGET_EXPOSURE`:

```text
target
target_label
long_value
short_value
net_value
gross_value
target_pct_pl
holdings_count
issuers_count
assets_count
top_issuer
top_asset_class
concentration_pct
```

## Temas analiticos

```text
foreign          -> Exterior
public_bonds     -> Titulos publicos
private_credit   -> Credito privado
fund_quotas      -> Cotas de fundos
equity           -> Acoes
derivatives      -> Derivativos
confidential     -> Confidencial
```

## Importacao inicial

A primeira construcao foi feita com limites conservadores:

```text
month: 202604
max_funds: 180
max_positions_per_fund: 20
min_abs_value: 25.000.000
target_funds_per_theme: 30
```

Resultado no Neo4j:

```text
CdaAsset: 677
CdaIssuer: 455
CdaFund: 180
CdaAssetClass: 9
CdaExposureTarget: 7
CdaCountry: 7
CdaFundType: 4
CdaMonth: 1

HOLDS_POSITION: 2011
ISSUED_BY: 746
LOCATED_IN: 678
CLASSIFIED_AS: 677
HAS_TARGET_EXPOSURE: 417
REPORTED_IN: 180
HAS_FUND_TYPE: 180
```

## Proximos passos sugeridos

1. Criar uma tela visual de grafo usando o contrato `nodes/edges` do endpoint `/network`.
2. Adicionar filtros de grafo por tema: exterior, credito privado, derivativos, confidencial.
3. Criar visual de crowding por emissor e ativo: fundos conectados ao mesmo emissor com gross exposure alto.
4. Adicionar camada temporal quando houver mais meses: variacao de posicao, novos fundos compradores, saida de fundos e mudanca de concentracao.
5. Usar OpenAI apenas para enriquecer labels e narrativas auditaveis a partir do payload do grafo, nao para criar posicoes.
