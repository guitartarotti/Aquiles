# Funds Flow Local - Relatorio de Dados e Possivel Tela de Grafo

Gerado em: 2026-05-27  
Projeto: MiroFish  
Modulo: Funds Flow Local  
Objetivo deste documento: entregar ao analista um inventario detalhado do que ja existe de dados no widget, como cada fonte entra no pipeline, quais campos e tabelas derivadas estao disponiveis, quais limitacoes ainda existem e como o grafo ja existente no projeto pode ser reaproveitado para uma tela especifica de grafo.

---

## 1. Resumo executivo

O widget Funds Flow Local hoje ja possui uma base relevante para analise de fluxo de fundos locais, fluxo/participacao B3, fluxo global ICI, posicionamento semanal CFTC e validacao ANBIMA.

O nucleo local vem da CVM:

- CVM Informe Diario FI: captacao, resgate, PL, cota e cotistas por fundo.
- CVM Cadastro FI: cadastro, situacao e metadados dos fundos.
- ANBIMA: consolidado diario e boletins, usado como camada de validacao e comparacao agregada.

As camadas complementares sao:

- B3: participacao por tipo de investidor, dados de mercado, fluxo estrangeiro mensal, volume por mercado e open interest de derivativos.
- ICI: fluxos globais semanais de mutual funds/ETFs e dados mundiais por pais/regiao.
- CFTC COT/TFF: posicionamento semanal por tipo de participante em contratos globais, com foco em asset managers, leveraged funds, dealers e outros participantes.
- BCB/FRED: configurados no contrato, mas ainda nao carregados no payload principal desta rodada.

Estado atual do dashboard consultado localmente:

- Data de corte: 2026-05-25.
- Data solicitada: 2026-05-27.
- Periodo padrao: 21d.
- Historico consultado: 95 dias.
- PL da industria: R$ 13.132,7 bi.
- Fluxo liquido 1d: -R$ 27,0 bi.
- Fluxo liquido 5d: -R$ 37,4 bi.
- Fluxo liquido 21d: -R$ 50,6 bi.
- Fluxo liquido YTD: R$ 18,1 bi.
- Cotistas: 25.833.836.
- Regime proprietario: stress.
- Pressure index: -2,1601.

Leitura rapida: a base ja permite montar uma tela de grafo institucional, mas a recomendacao e separar dois usos:

1. Grafo analitico deterministico: criado diretamente a partir das tabelas do Funds Flow Local, com nos e arestas calculados por metricas financeiras.
2. Grafo semantico/memoria: usando o Graphiti/Zep ja existente para guardar narrativas, relatorios diarios e relacoes textuais.

Para o produto final, o grafo analitico deve ser a tela principal. O Graphiti/Zep pode ficar como camada auxiliar de memoria e explicacao.

---

## 2. Estrutura atual do widget

O widget Funds Flow Local ja esta estruturado em abas:

- Overview: KPIs, fluxo por classe, rankings, leitura automatica e regime.
- B3: participacao de investidores, dados de mercado, fluxo estrangeiro mensal e open interest.
- Mapa: heatmap por classe/tempo.
- Stress: indicadores de resgate, concentracao e pressao.
- ANBIMA: consolidado diario, boletins, validacao contra CVM e rankings.
- ICI: fluxos globais e dados por pais/regiao.
- CFTC: posicionamento semanal por participante e contrato.
- Fontes: status, detalhe, ultima captura e botao para forcar atualizacao.

Endpoint principal:

```text
GET /api/v1/funds-flow-local/dashboard?period=21d&history_days=95
```

Arquivo de amostra do payload:

```text
backend/uploads/macro/funds_flow_local/derived/dashboard_payload.schema_sample.json
```

O frontend nao consulta fontes externas diretamente. Ele consome o payload consolidado do backend.

---

## 3. Status das fontes

### 3.1 CVM Informe Diario FI

Status: ativo.  
Papel: fonte primaria para fluxo diario por fundo.  
Linhas carregadas: 1.926.622.  
Meses carregados: 202602, 202603, 202604, 202605.  
Arquivo bruto principal:

```text
backend/uploads/macro/funds_flow_local/raw/cvm_informe/inf_diario_fi_202605.zip
```

Campos principais esperados:

- CNPJ_FUNDO
- DT_COMPTC
- VL_TOTAL
- VL_QUOTA
- VL_PATRIM_LIQ
- CAPTC_DIA
- RESG_DIA
- NR_COTST

Uso:

- Calcula captacao liquida diaria.
- Calcula fluxo como percentual do PL defasado.
- Calcula retorno da cota.
- Calcula variacao de cotistas.
- Agrega fluxo por classe, fundo, gestor e estrategia.

Formulas principais:

```text
captacao_liquida = CAPTC_DIA - RESG_DIA
flow_pct_pl = captacao_liquida / PL_t-1
quota_return = ln(VL_QUOTA_t / VL_QUOTA_t-1)
delta_cotistas = NR_COTST_t - NR_COTST_t-1
```

Granularidade:

- Fundo individual.
- CNPJ.
- Data diaria.
- Classe ou categoria apos join com cadastro/classificador.

Limitacoes:

- A CVM publica arquivos mensais. A ultima data util disponivel pode ficar abaixo da data corrente.
- Algumas classificacoes podem cair em "Unclassified" quando o cadastro/classificador nao resolve a classe.
- Fluxo diario de fundos nao deve ser confundido com negociacao secundaria de ETFs ou acoes.

### 3.2 CVM Cadastro FI

Status: ativo.  
Papel: universo, metadados e classificacao cadastral.  
Linhas carregadas: 75.410.  
Arquivos brutos:

```text
backend/uploads/macro/funds_flow_local/raw/cvm_cadastro/registro_fundo_classe.zip
backend/uploads/macro/funds_flow_local/raw/cvm_cadastro/cad_fi.csv
```

Campos/atributos usados ou esperados:

- CNPJ do fundo.
- Nome do fundo.
- Situacao.
- Data de registro.
- Data de constituicao/inicio.
- Administrador.
- Gestor.
- Classe CVM.
- Tipo de fundo.
- Indicadores de adaptacao RCVM 175 quando disponiveis.

Uso:

- Cruza CNPJ do informe diario com metadados.
- Filtra fundos ativos/inativos.
- Alimenta classificacao por macro classe.
- Ajuda a montar rankings por gestor e administrador.

Limitacoes:

- A classificacao ANBIMA nem sempre vem completa no arquivo local usado.
- Quando nao ha classificacao direta, o pipeline usa fallback por nome/classe/tipo e atribui confidence_score.

### 3.3 ANBIMA Fundos

Status: ativo.  
Papel: validacao agregada e benchmark de consistencia.  
Linhas carregadas no consolidado: 152.  
Referencia: 2026-05-22.  
Arquivo bruto:

```text
backend/uploads/macro/funds_flow_local/raw/anbima/consolidado_diario/20260522.xlsx
```

O que traz:

- Consolidado por categoria.
- Consolidado por tipo ANBIMA.
- Patrimonio liquido.
- Participacao no PL.
- Captacao liquida no dia.
- Captacao liquida no mes.
- Captacao liquida no ano.
- Captacao liquida em 12 meses.
- Rentabilidade por dia, mes, ano e 12 meses, quando disponivel.
- Boletins/noticias mensais com leitura textual da industria.

Tabelas derivadas:

```text
anbima_categories.csv
anbima_types.csv
anbima_cvm_validation.csv
anbima_ranking_administrators.csv
anbima_ranking_managers.csv
anbima_top_type_inflows_mtd.csv
anbima_top_type_outflows_mtd.csv
anbima_bulletin_articles.csv
```

Uso:

- Validar se a soma CVM por macro classe esta coerente com ANBIMA.
- Exibir leitura oficial por categoria/tipo.
- Listar tipos com maior entrada/saida no mes.
- Enriquecer comentario automatico com boletins mensais.

Limitacoes:

- A data ANBIMA pode nao coincidir exatamente com a ultima data CVM.
- O universo ANBIMA e o universo CVM podem divergir por regra de classificacao, fechamento ou escopo.
- A fonte e usada como benchmark, nao como fonte primaria de captacao por fundo.

### 3.4 B3 - Participacao de investidores, dados de mercado e derivativos

Status: ativo.  
Papel: camada de mercado secundario, participacao por tipo de investidor e open interest.  
Historico BDI/participacao: 105 linhas.  
Tendencia por participante: 5 linhas.  
Participacao mensal: 5 linhas.  
Market data report: ativo.  
Open interest: ativo.  
Historico de open interest: 147 linhas.  
Contratos recentes de open interest: 128 linhas.

Arquivos derivados:

```text
b3_history.csv
b3_trend_by_participant.csv
b3_daily_reports.csv
b3_investor_participation_monthly.csv
b3_market_data_average_daily_trading_value.csv
b3_market_data_daily_average_trades.csv
b3_market_data_foreign_investor_flow_monthly.csv
b3_market_data_investor_participation_monthly.csv
b3_market_data_total_trades.csv
b3_market_data_trading_volume_monthly.csv
b3_open_interest_history.csv
b3_open_interest_latest_contracts.csv
b3_open_interest_product_summary.csv
b3_open_interest_futures_summary.csv
```

#### B3 BDI / participacao diaria por investidor

Arquivo:

```text
b3_history.csv
```

Campos:

- date
- publication_date
- participant_type
- buy_brl_mtd
- sell_brl_mtd
- net_flow_brl_mtd
- turnover_brl_mtd
- daily_buy_brl
- daily_sell_brl
- daily_net_flow_brl
- buy_participation_pct
- sell_participation_pct

Participantes esperados:

- Investidor estrangeiro.
- Investidor institucional.
- Pessoas fisicas.
- Instituicoes financeiras.
- Outros.

Uso:

- Medir compra/venda liquida por tipo de investidor.
- Separar fluxo CVM de fundos de fluxo secundario B3.
- Comparar pressao de fundos locais com fluxo estrangeiro/institucional/pessoa fisica.
- Criar graficos por participante no Overview e na aba B3.

Limitacoes:

- O BDI reflete negociacao secundaria e acumulados do mes, nao captacao/resgate de fundos.
- Houve erro pontual em PDF de 2026-05-01 com HTTP 500, mas a fonte geral esta ativa.

#### B3 participacao mensal por mercado

Arquivo:

```text
b3_investor_participation_monthly.csv
```

Campos:

- participant_type
- cash_brl
- cash_participation_pct
- forward_brl
- forward_participation_pct
- options_brl
- options_participation_pct
- options_exercise_brl
- options_exercise_participation_pct
- blocks_brl
- blocks_participation_pct
- total_brl
- total_participation_pct

Uso:

- Mostrar contribuicao de cada tipo de investidor no volume mensal.
- Separar mercado a vista, termo, opcoes, exercicio de opcoes e blocos.
- Criar uma leitura estrutural de composicao de volume.

#### B3 market data report

Arquivos:

```text
b3_market_data_trading_volume_monthly.csv
b3_market_data_total_trades.csv
b3_market_data_average_daily_trading_value.csv
b3_market_data_daily_average_trades.csv
b3_market_data_investor_participation_monthly.csv
b3_market_data_foreign_investor_flow_monthly.csv
```

Dados disponiveis:

- Volume mensal negociado por mercado.
- Numero total de negocios.
- Media diaria de volume financeiro.
- Media diaria de negocios.
- Participacao mensal por investidor.
- Fluxo estrangeiro mensal: compras, vendas, IPO/follow-on e saldo.

Uso:

- Criar visao macro B3 de liquidez e atividade.
- Mostrar se o fluxo estrangeiro esta comprador/vendedor no mes.
- Contextualizar BDI diario com uma fotografia mensal.

#### B3 open interest de derivativos

Arquivos:

```text
b3_open_interest_history.csv
b3_open_interest_latest_contracts.csv
b3_open_interest_product_summary.csv
b3_open_interest_futures_summary.csv
```

Produtos/contratos relevantes:

- DI1.
- DDI.
- DOL.
- WDO.
- WIN.
- Outros contratos de futuros disponiveis na captura.

Uso:

- Expor contratos de juros, dolar e indice no frontend.
- Mostrar open interest por produto e contrato.
- Comparar variacao de open interest com fluxo por participante e regime de mercado.

Limitacoes:

- Open interest e posicao em aberto, nao fluxo financeiro direto.
- Para inferir "quem esta comprado/vendido" por participante em DI, DOL, WDO e WIN, e necessario confirmar se a B3 expõe esse breakdown por participante em endpoint publico. O que esta carregado hoje cobre open interest e participacao/volume; a camada "posicao por participante por contrato" precisa de validacao adicional.

### 3.5 ICI - fluxos globais e comparacao internacional

Status: ativo.  
Papel: fluxo global de mutual funds/ETFs e base mundial por pais/regiao.  
Weekly rows: 304.  
Paises: 45.  
Regioes: 5.

Arquivos derivados:

```text
ici_weekly_series.csv
ici_monthly_series.csv
ici_monthly_etf_assets_by_type.csv
ici_monthly_etf_issuance.csv
ici_worldwide_countries.csv
ici_worldwide_regions.csv
ici_worldwide_top_country_etf_net_sales.csv
ici_worldwide_bottom_country_etf_net_sales.csv
```

#### ICI weekly series

Arquivo:

```text
ici_weekly_series.csv
```

Campos:

- date
- vehicle
- vehicle_label
- category
- category_key
- category_group
- flow_usd_mn
- frequency
- data_kind

Uso:

- Mostrar fluxo global semanal por segmento.
- Separar mutual funds e ETFs quando a fonte permitir.
- Criar tabela de inflow/outflow com verde/vermelho.
- Selecionar series para grafico historico interativo.

#### ICI worldwide countries

Arquivo:

```text
ici_worldwide_countries.csv
```

Campos principais:

- level
- region
- country
- assets_total_usd_mn
- assets_equity_usd_mn
- assets_bond_usd_mn
- assets_balanced_mixed_usd_mn
- assets_money_market_usd_mn
- net_sales_total_usd_mn
- net_sales_equity_usd_mn
- net_sales_bond_usd_mn
- net_sales_balanced_mixed_usd_mn
- net_sales_money_market_usd_mn
- fund_count_total_count
- fund_count_equity_count
- fund_count_bond_count
- fund_count_balanced_mixed_count
- fund_count_money_market_count
- assets_etfs_usd_mn
- assets_institutional_funds_usd_mn
- net_sales_etfs_usd_mn
- net_sales_institutional_funds_usd_mn
- fund_count_etfs_count
- fund_count_institutional_funds_count

Uso:

- Lista completa de inflow/outflow por pais.
- Heatmap por pais/regiao.
- Ranking de net sales por tipo de fundo.
- Comparacao Brasil versus mundo, sem misturar ainda com CVM.

#### ICI worldwide regions

Arquivo:

```text
ici_worldwide_regions.csv
```

Uso:

- Agregacao por regiao.
- Heatmap regional.
- Ranking de entradas/saidas globais.
- Base para "risk appetite global".

Limitacoes:

- ICI mistura frequencias: semanal, mensal e trimestral/mundial.
- Dados por pais/regiao nem sempre sao semanais.
- Deve ficar claro no frontend quando o dado e semanal versus trimestral/mundial.

### 3.6 CFTC COT/TFF

Status: ativo.  
Papel: posicionamento semanal global, nao fund flow primario.  
Linhas carregadas: 18.884.  
Contratos foco: 38.  
Participantes: 5.  
Buckets: 6.  
Data do relatorio: 2026-05-19.  
Publicacao: 2026-05-22.

Arquivos derivados:

```text
cftc_tff_weekly_series.csv
cftc_tff_latest_contracts.csv
cftc_tff_focus_contracts.csv
cftc_tff_participant_summary.csv
cftc_tff_asset_bucket_summary.csv
```

Frequencia:

- Semanal.
- Posicoes de terca-feira.
- Divulgacao normalmente na sexta-feira.

Participantes principais:

- Asset Manager/Institutional.
- Leveraged Funds.
- Dealer/Intermediary.
- Other Reportables.
- Nonreportables.

Campos relevantes nos contratos foco:

- date
- contract_code
- market_name
- market_and_exchange_names
- commodity_subgroup
- asset_bucket
- open_interest
- open_interest_change
- dealer_net
- dealer_change_net
- dealer_pct_oi_net
- asset_mgr_net
- asset_mgr_change_net
- asset_mgr_pct_oi_net
- asset_mgr_net_zscore_156w
- asset_mgr_net_percentile_156w
- lev_money_net
- lev_money_change_net
- lev_money_pct_oi_net
- lev_money_net_zscore_156w
- lev_money_net_percentile_156w
- other_rept_net
- nonrept_net
- concentration_gross_4_long
- concentration_gross_4_short

Uso:

- Mostrar posicionamento global por contrato e bucket.
- Separar CTAs/leveraged funds de asset managers.
- Comparar equity index, financial futures, rates, FX e commodities.
- Criar painel "Global Positioning Proxy".

Limitacoes:

- Nao e fluxo diario.
- Nao deve ser apresentado como captacao/resgate.
- E proxy de posicionamento, nao dados de fundos.
- Para tela de grafo, deve entrar como relacao "participante posicionado em contrato", nao como fluxo financeiro local.

### 3.7 BCB e FRED

Status: configurados, mas ainda sem carga ativa no dashboard principal desta rodada.  
Papel planejado: macro local e macro global.

BCB planejado:

- Selic.
- Cambio.
- Focus.
- Reservas.
- Fluxo cambial.
- Series SGS/OData.

FRED planejado:

- Treasury 2Y, 5Y, 10Y.
- Breakevens.
- Brent.
- Outros proxies globais.

Uso futuro:

- Correlacao fluxo local x juros/cambio.
- Explicacao de rotacao entre renda fixa, acoes e multimercado.
- Ligacao Brasil x global.
- Arestas de grafo do tipo "coincide com", "correlacionado com" ou "pressionado por", sempre sem causalidade forte.

---

## 4. Tabelas derivadas locais do Funds Flow

Diretorio:

```text
backend/uploads/macro/funds_flow_local/derived
```

### 4.1 flow_by_class.csv

Linhas: 767.  
Uso: serie diaria por macro classe.  
Campos:

- date
- macro_classe
- net_flow
- rolling_flow_5d
- rolling_flow_21d
- rolling_flow_63d
- flow_pct_pl
- flow_pct_pl_21d
- zscore
- pressure_index
- aum
- num_funds

Leituras possiveis:

- Fluxo acumulado por classe.
- Z-score de entrada/saida.
- Pressao de fluxo.
- Evolucao de PL por classe.
- Regime por classe.

### 4.2 industry_flow.csv

Linhas: 73.  
Uso: serie diaria agregada da industria.  
Campos:

- date
- net_flow
- rolling_flow_5d
- rolling_flow_21d
- rolling_flow_63d
- pressure_index
- aum
- cotistas

Leituras possiveis:

- Stress agregado.
- Entrada/saida da industria.
- PL total.
- Cotistas totais.
- Tendencia de curto prazo.

### 4.3 monthly_stacked_flow.csv

Linhas: 44.  
Uso: barras empilhadas mensais por classe.  
Campos:

- month
- macro_classe
- net_flow_month
- aum

Leituras possiveis:

- Rotacao estrutural entre classes.
- Meses de concentracao de entrada/saida.
- Mudanca de regime entre meses.

### 4.4 ranking_by_class.csv

Linhas: 11.  
Uso: ranking por macro classe.  
Campos:

- rank
- name
- level
- net_flow_1d
- net_flow_5d
- net_flow_21d
- flow_pct_pl_21d
- zscore_21d
- aum
- share_pl_industry
- pressure_index
- num_funds

Leituras possiveis:

- Maior entrada e maior saida.
- Peso no PL da industria.
- Fluxo percentual por classe.
- Classes em stress.

### 4.5 ranking_by_fund.csv

Linhas: 20.  
Uso: top fundos por entrada/saida.  
Campos:

- rank
- name
- cnpj_fundo
- level
- macro_classe
- net_flow_1d
- net_flow_5d
- net_flow_21d
- flow_pct_pl_21d
- aum
- cotistas
- delta_cotistas
- classification_confidence

Leituras possiveis:

- Fundos que mais puxam o fluxo.
- Concentracao de resgates/captacoes.
- Queda/subida de cotistas.
- Confianca da classificacao.

### 4.6 ranking_by_manager.csv

Linhas: 20.  
Uso: ranking por gestor.  
Campos:

- rank
- name
- level
- net_flow_1d
- net_flow_21d
- aum
- cotistas
- num_funds

Leituras possiveis:

- Gestores com entrada/saida liquida.
- Gestores relevantes por PL.
- Concentracao por casa.

### 4.7 ranking_by_strategy_tag.csv

Linhas: 11.  
Uso: ranking por estrategia/tag.  
Campos:

- rank
- name
- level
- net_flow_1d
- net_flow_21d
- aum
- cotistas
- num_funds

Leituras possiveis:

- Rotacao por tag de estrategia.
- Entrada/saida em classes inferidas.
- Identificacao de segmentos pressionados.

---

## 5. Dados atuais de maior valor analitico

### 5.1 Para fluxo local

Mais importantes:

- net_flow_1d
- net_flow_5d
- net_flow_21d
- net_flow_ytd
- flow_pct_pl_21d
- zscore_21d
- pressure_index
- aum
- cotistas
- delta_cotistas
- num_funds

Melhores cortes:

- Macro classe.
- Fundo.
- Gestor.
- Strategy tag.
- Administrador.

Perguntas que ja da para responder:

- Para onde esta indo o dinheiro na industria local?
- Qual classe esta recebendo ou perdendo recursos?
- O fluxo e nominalmente grande ou grande como percentual do PL?
- A saida esta concentrada em poucos fundos ou espalhada?
- Existe queda de cotistas acompanhando resgate?
- O regime da industria esta em entrada, neutro, resgate ou stress?

### 5.2 Para B3

Mais importantes:

- daily_net_flow_brl por tipo de investidor.
- buy_participation_pct e sell_participation_pct.
- net_flow_brl_mtd.
- total_participation_pct mensal por mercado.
- foreign_investor_flow_monthly.
- open_interest por produto/contrato.
- open_interest_change.

Melhores cortes:

- Investidor estrangeiro.
- Investidor institucional.
- Pessoa fisica.
- Instituicoes financeiras.
- Outros.
- Mercado a vista, termo, opcoes, exercicio, blocos.
- Contratos DI1, DDI, DOL, WDO, WIN.

Perguntas que ja da para responder:

- Estrangeiro esta comprador ou vendedor no mercado secundario?
- Institucional local esta em direcao oposta?
- Pessoa fisica ganhou/perdeu participacao?
- Liquidez mensal subiu ou caiu?
- Open interest em juros, dolar e indice esta aumentando?

### 5.3 Para ICI

Mais importantes:

- weekly flow_usd_mn por categoria.
- net_sales_total_usd_mn por pais.
- net_sales_equity_usd_mn.
- net_sales_bond_usd_mn.
- net_sales_money_market_usd_mn.
- net_sales_etfs_usd_mn.
- assets_total_usd_mn.
- assets_etfs_usd_mn.
- fund_count_total_count.

Melhores cortes:

- Pais.
- Regiao.
- Equity.
- Bond.
- Mixed.
- Money market.
- ETF.
- Institutional funds.

Perguntas que ja da para responder:

- Quais paises/regioes tiveram inflow/outflow?
- Quais segmentos globais estao recebendo recursos?
- ETFs estao captando ou perdendo?
- Brasil esta em linha ou divergente da fotografia global?

### 5.4 Para CFTC

Mais importantes:

- open_interest.
- open_interest_change.
- asset_mgr_net.
- asset_mgr_change_net.
- asset_mgr_pct_oi_net.
- lev_money_net.
- lev_money_change_net.
- lev_money_pct_oi_net.
- dealer_net.
- dealer_change_net.
- net_zscore_156w.
- net_percentile_156w.

Melhores cortes:

- Asset bucket.
- Contrato.
- Participante.
- Commodity subgroup.
- Equity index.
- Financial futures.
- FX/rates/commodities quando disponiveis.

Perguntas que ja da para responder:

- Leveraged funds estao comprados ou vendidos em determinado contrato?
- Asset managers estao em extremo historico?
- Open interest subiu junto com mudanca de posicao?
- Existe concentracao nos quatro maiores long/short?

---

## 6. Qualidade, lacunas e cuidados de interpretacao

1. CVM e a fonte primaria de captacao/resgate de fundos locais.
2. B3 e fonte de mercado secundario, participacao, volume e open interest. Nao substitui CVM para fluxo de fundos.
3. ANBIMA e benchmark/validacao. Pode divergir da CVM por data, regra, universo e classificacao.
4. ICI tem frequencias misturadas. Weekly flows nao devem ser misturados sem marcacao com dados mundiais trimestrais/mensais.
5. CFTC e semanal e representa posicionamento, nao fluxo diario.
6. BCB/FRED ainda estao configurados, mas precisam ser ativados para grafo macro completo.
7. Nao afirmar causalidade. Usar linguagem como "coincide com", "esta associado a", "diverge de" ou "acompanha".
8. Para fundos individuais, limitar visualizacao a top N para nao gerar ruido e problemas de performance.
9. Para grafo, nao colocar todas as series historicas como nos. Series devem virar metricas/atributos ou arestas agregadas.

---

## 7. O grafo que ja existe no projeto

O projeto ja possui uma infraestrutura de grafo reutilizavel.

### 7.1 Frontend

Componente:

```text
frontend/src/components/GraphPanel.vue
```

API client:

```text
frontend/src/api/graph.js
```

Caracteristicas do GraphPanel:

- Usa D3.
- Renderiza SVG.
- Usa forceSimulation.
- Suporta zoom.
- Suporta drag de nos.
- Renderiza nodes e edges.
- Tem legendas por tipo de entidade.
- Tem painel lateral de detalhe.
- Mostra atributos, resumo, labels e datas.
- Mostra detalhes de arestas: fact, fact_type, valid_at, created_at e episodes.
- Trata self-loops.
- Aceita um objeto graphData com nodes e edges.

Formato esperado de alto nivel:

```json
{
  "graph_id": "string",
  "nodes": [],
  "edges": [],
  "node_count": 0,
  "edge_count": 0
}
```

Formato tipico de node:

```json
{
  "uuid": "string",
  "name": "string",
  "labels": ["EntityType"],
  "summary": "string",
  "attributes": {},
  "created_at": "datetime"
}
```

Formato tipico de edge:

```json
{
  "uuid": "string",
  "name": "string",
  "fact": "string",
  "fact_type": "RELATION_TYPE",
  "source_node_uuid": "string",
  "target_node_uuid": "string",
  "source_node_name": "string",
  "target_node_name": "string",
  "attributes": {},
  "created_at": "datetime",
  "valid_at": "datetime",
  "invalid_at": null,
  "expired_at": null,
  "episodes": []
}
```

Endpoints existentes:

```text
POST /api/graph/ontology/generate
POST /api/graph/build
GET  /api/graph/task/:taskId
GET  /api/graph/data/:graphId
GET  /api/graph/project/:projectId
```

### 7.2 Backend

Arquivos principais:

```text
backend/app/api/graph.py
backend/app/services/graph_builder.py
backend/app/services/graph_backends/graphiti_local.py
```

Servico:

```text
GraphBuilderService
```

Backends:

- zep_cloud.
- graphiti_local.

O backend Graphiti Local usa:

```text
graphiti-local/backend_bridge.py
graphiti-local/.venv
backend/uploads/graphiti_graphs
```

O backend cria metadados em:

```text
backend/uploads/graphiti_graphs/graphiti_*.json
```

Exemplo existente:

```text
backend/uploads/graphiti_graphs/graphiti_be346ed2ca9c4626.json
```

Nome do grafo existente:

```text
Macro Live Feed
```

Esse grafo possui uma ontologia de macro/mercado.

### 7.3 Ontologia existente do Macro Live Feed

Entity types vistos no grafo existente:

- Contract: contrato listado de futuros ou juros.
- Security: ativo spot/equity usado como referencia.
- Broker: participante/corretora/ranking de mercado.
- NewsSource: fonte que publica noticia.
- NewsEvent: evento/noticia macro.
- MacroTheme: tema macro.
- Country: pais.
- ParticipantFlowSnapshot: snapshot de fluxo por participante.
- MarketMoveWindow: janela de movimento de mercado.
- NewsImpactLink: ligacao entre noticia e impacto.

Edge types vistos no grafo existente:

- PUBLISHED_BY.
- RELATES_TO_CONTRACT.
- RELATES_TO_THEME.
- HAS_PARTICIPANT.
- SUMMARIZED_BY_FLOW.
- MOVED_IN_WINDOW.
- IMPACTS_CONTRACT.
- QUOTES_SECURITY.
- FOCUSES_ON_COUNTRY.

Leitura: o grafo atual e bom para relacionar noticias, temas, contratos, paises, participantes e movimentos. Ele foi pensado para um feed macro e nao exatamente para fluxo de fundos, mas a estrutura visual e tecnica pode ser reaproveitada.

---

## 8. Podemos usar esse grafo para uma tela de grafo do Funds Flow?

Sim, mas com uma adaptacao importante.

O GraphPanel existente e reaproveitavel como base visual. Ele ja resolve o problema de:

- desenhar nos/arestas;
- zoom;
- drag;
- detalhe lateral;
- legenda;
- visualizacao de atributos;
- integracao com payload de grafo.

Porem, o pipeline Graphiti/Zep nao deve ser o unico motor para dados financeiros tabulares. O motivo: nossos dados principais sao series numericas e snapshots agregados. Eles precisam de determinismo, filtros, pesos e datas. Se mandarmos todo o historico como texto para um grafo semantico, perdemos controle sobre:

- peso das arestas;
- metricas financeiras;
- reproducibilidade;
- top N;
- filtros por periodo;
- diferenca entre fluxo, posicao, volume e open interest;
- consistencia diaria.

Recomendacao:

1. Criar um endpoint deterministico:

```text
GET /api/v1/funds-flow-local/graph?period=21d&level=overview&top_n=20
```

2. Esse endpoint deve ler as tabelas/payload ja existentes e emitir nodes/edges no formato que o GraphPanel ja entende.

3. O Graphiti/Zep pode continuar como camada semantica opcional para ingestao dos relatorios diarios e insights textuais.

---

## 9. Proposta de grafo especifico para Funds Flow Local

### 9.1 Tipos de nos recomendados

Source:

- CVM.
- ANBIMA.
- B3.
- ICI.
- CFTC.
- BCB.
- FRED.

Dataset:

- CVM Informe Diario.
- CVM Cadastro FI.
- ANBIMA Consolidado Diario.
- B3 BDI.
- B3 Market Data CSV.
- B3 Open Interest.
- ICI Weekly Flows.
- ICI Worldwide Countries.
- CFTC TFF.

LocalFundClass:

- Renda Fixa.
- Acoes.
- Multimercado.
- Previdencia.
- Cambial.
- ETF.
- FIDC.
- FIP.
- FII.
- Fiagro.
- Outros.
- Unclassified.

Fund:

- Apenas top N de entrada/saida.

Manager:

- Apenas top N por fluxo/PL.

StrategyTag:

- Tags agregadas ja existentes.

B3Participant:

- Estrangeiro.
- Institucional.
- Pessoa fisica.
- Instituicao financeira.
- Outros.

Contract/Product:

- DI1.
- DDI.
- DOL.
- WDO.
- WIN.
- Outros contratos relevantes.

GlobalCategory:

- ICI equity.
- ICI bond.
- ICI money market.
- ICI ETF.
- ICI mixed/balanced.

Country/Region:

- Paises ICI.
- Regioes ICI.

CFTCParticipant:

- Asset Manager/Institutional.
- Leveraged Funds.
- Dealer/Intermediary.
- Other Reportables.
- Nonreportables.

Signal/Regime:

- Stress.
- Resgate relevante.
- Entrada relevante.
- Fluxo neutro.
- Divergencia local/global.
- Concentracao de resgates.
- Open interest subindo.
- Posicionamento extremo.

### 9.2 Tipos de arestas recomendados

PROVIDES:

- Source -> Dataset.
- Exemplo: CVM PROVIDES Informe Diario.

OBSERVES:

- Dataset -> Entity.
- Exemplo: B3 BDI OBSERVES Estrangeiro.

HAS_FLOW:

- LocalFundClass/Fund/Manager -> Metric/Signal.
- Atributos: net_flow_1d, net_flow_21d, flow_pct_pl_21d, zscore_21d.

VALIDATES:

- ANBIMA -> CVM aggregation.
- Atributos: aum_diff_pct, flow_diff_brl.

PARTICIPATES_IN:

- B3Participant -> Market/Product.
- Atributos: buy_pct, sell_pct, net_flow_brl.

HAS_OPEN_INTEREST:

- Contract/Product -> OpenInterestSignal.
- Atributos: open_interest, open_interest_change.

POSITIONED_IN:

- CFTCParticipant -> Contract.
- Atributos: net, change_net, pct_oi_net, zscore_156w, percentile_156w.

COUNTRY_FLOW:

- ICI -> Country.
- Atributos: net_sales_total_usd_mn, net_sales_equity_usd_mn, net_sales_bond_usd_mn, net_sales_etfs_usd_mn.

REGION_FLOW:

- ICI -> Region.
- Atributos similares aos paises.

DIVERGES_FROM:

- LocalClass -> GlobalCategory.
- Exemplo: Acoes Brasil DIVERGES_FROM ICI Global Equity.
- Usar apenas quando regra numerica clara existir.

ROTATES_TO:

- LocalClass -> LocalClass.
- Exemplo: Acoes ROTATES_TO Renda Fixa quando zscore RF positivo e zscore Acoes negativo.

SIGNALS_STRESS:

- Classe/Fundo/Gestor -> Stress.
- Atributos: pressure_index, pct_funds_negative, hhi_redemptions.

CORRELATED_WITH:

- Fluxo local -> serie macro.
- Usar somente quando BCB/FRED estiverem ativos e houver calculo explicito.

### 9.3 Pesos e cores

Sugestao:

- Tamanho do no de classe: PL ou abs(net_flow_21d).
- Cor do no de classe: regime/pressure_index.
- Espessura da aresta de fluxo: abs(net_flow_21d).
- Cor da aresta: verde para inflow, vermelho para outflow, cinza para neutro.
- Tamanho do no de pais/regiao: assets_total_usd_mn.
- Cor do pais/regiao: net_sales_total_usd_mn positivo/negativo.
- Tamanho do no de contrato: open_interest.
- Cor do contrato: open_interest_change ou sinal do participante dominante.

### 9.4 Filtros recomendados

- Periodo: 1d, 5d, 21d, 63d, YTD.
- Nivel: fonte, classe, fundo, gestor, participante, contrato, pais, regiao.
- Top N: 10, 20, 50.
- Fonte: CVM, ANBIMA, B3, ICI, CFTC.
- Mostrar/ocultar dados configurados.
- Mostrar apenas inflow, apenas outflow ou ambos.
- Mostrar apenas stress.
- Mostrar apenas divergencias local/global.

### 9.5 Telas de grafo possiveis

Grafo 1 - Lineage das fontes:

- Objetivo: mostrar de onde cada dado vem.
- Nos: Source, Dataset, Metric.
- Arestas: PROVIDES, OBSERVES.
- Uso: auditoria, confianca e explicacao para usuario institucional.

Grafo 2 - Fluxo local e stress:

- Objetivo: entender classes, fundos e gestores pressionados.
- Nos: LocalFundClass, Fund, Manager, Signal.
- Arestas: HAS_FLOW, SIGNALS_STRESS, ROTATES_TO.
- Uso: principal para dashboard Funds Flow Local.

Grafo 3 - B3 participantes e contratos:

- Objetivo: conectar investidor estrangeiro/institucional/PF com mercados e contratos.
- Nos: B3Participant, Market, Product/Contract, OpenInterestSignal.
- Arestas: PARTICIPATES_IN, HAS_OPEN_INTEREST.
- Uso: aba B3 e leitura de fluxo secundario.

Grafo 4 - Global/ICI:

- Objetivo: paises, regioes e segmentos globais com inflow/outflow.
- Nos: Region, Country, GlobalCategory.
- Arestas: COUNTRY_FLOW, REGION_FLOW.
- Uso: aba ICI.

Grafo 5 - CFTC posicionamento:

- Objetivo: participantes globais e contratos com posicao extrema.
- Nos: CFTCParticipant, Contract, AssetBucket.
- Arestas: POSITIONED_IN.
- Uso: aba CFTC.

Grafo 6 - Grafo combinado:

- Objetivo: narrativa completa, mas com agregacao forte.
- Nos: Source, Dataset, LocalClass, B3Participant, Contract, GlobalCategory, Country, CFTCParticipant, Signal.
- Uso: tela executiva, com filtros obrigatorios para nao virar ruido.

---

## 10. Melhor caminho tecnico

### Fase 1 - Grafo analitico deterministico

Criar endpoint:

```text
GET /api/v1/funds-flow-local/graph
```

Parametros:

```text
period=21d
history_days=95
level=overview|local|b3|ici|cftc|sources
top_n=20
metric=net_flow|flow_pct_pl|zscore|pressure_index|open_interest|net_sales
```

Saida:

```json
{
  "graph_id": "funds_flow_local_2026-05-25_21d",
  "nodes": [],
  "edges": [],
  "node_count": 0,
  "edge_count": 0,
  "as_of_date": "2026-05-25",
  "period": "21d",
  "lineage": {}
}
```

Vantagens:

- Deterministico.
- Rapido.
- Auditavel.
- Usa tabelas ja existentes.
- Reaproveita GraphPanel.
- Permite cores/pesos por metrica.

### Fase 2 - Tela de grafo no frontend

Criar aba:

```text
Grafo
```

Ou tela especifica:

```text
/funds-flow-local/graph
```

Componentes:

- Toolbar de filtros.
- GraphPanel adaptado.
- Painel lateral de detalhes financeiros.
- Legenda de fontes e tipos de no.
- Exportacao JSON/CSV.
- Botao "gerar narrativa do grafo".

Mudancas desejaveis no GraphPanel:

- Aceitar edge weight para espessura.
- Aceitar edge color vindo do backend.
- Aceitar node size vindo do backend.
- Melhorar labels longos, porque hoje labels podem truncar demais.
- Permitir clusters por tipo.
- Permitir filtro por tipo de node/edge.
- Permitir layout radial ou por camadas para lineage.

### Fase 3 - Grafo semantico opcional

Gerar diariamente um resumo Markdown do Funds Flow Local e mandar para Graphiti/Zep:

- Snapshot do dia.
- Principais entradas/saidas.
- Eventos de stress.
- Divergencias local/global.
- Alertas B3.
- Alertas CFTC.

Uso:

- Perguntas em linguagem natural.
- Memoria historica.
- Explicacao narrativa.
- Relatorio para analista.

Nao usar para:

- Calculo de metricas.
- Ranking oficial.
- Valores finais exibidos no dashboard.

---

## 11. Recomendacao para o analista

Pedir ao analista para escolher qual problema o grafo deve resolver primeiro:

1. Auditoria de fonte e linhagem dos dados.
2. Mapa de stress por classe/fundo/gestor.
3. Rotacao entre classes locais.
4. Participantes B3 e contratos futuros.
5. ICI global por pais/regiao/segmento.
6. CFTC posicionamento por participante/contrato.
7. Grafo combinado de narrativa executiva.

Para cada grafo, o analista deve definir:

- Quais tipos de nos entram.
- Quais tipos de arestas existem.
- Qual metrica vira peso.
- Qual metrica vira cor.
- Qual periodo padrao.
- Qual limite de top N.
- Se a tela e para investigacao ou para leitura executiva.
- Como diferenciar fluxo, volume, posicao e open interest.

Minha sugestao como primeira entrega:

```text
Grafo 2 - Fluxo local e stress
```

Motivo:

- Esta diretamente ligado ao objetivo central do Funds Flow Local.
- Usa CVM, que e a fonte primaria mais robusta.
- Ja temos ranking, pressure_index, fluxo 21d, zscore e PL.
- Pode ser expandido depois para B3, ICI e CFTC.

Segunda entrega sugerida:

```text
Grafo 3 - B3 participantes e contratos
```

Motivo:

- O usuario ja pediu foco em B3.
- Ja temos participacao por investidor e open interest.
- Da para conectar investidor estrangeiro/institucional/PF com mercado e contratos.

Terceira entrega:

```text
Grafo 4 - Global/ICI
```

Motivo:

- Permite heatmap/lista por pais e regiao.
- Complementa a leitura local com contexto internacional.

---

## 12. Entregavel sugerido para proxima implementacao

Backend:

- Criar `funds_flow_local_graph.py`.
- Criar funcao que le o payload/tabelas derivadas.
- Criar builder de nodes/edges.
- Criar endpoint `/api/v1/funds-flow-local/graph`.
- Criar testes de schema do graph payload.

Frontend:

- Criar aba `Grafo`.
- Reutilizar `GraphPanel.vue`.
- Adicionar filtros de periodo, fonte, nivel, top N e metrica.
- Adaptar cores/tamanhos por atributos vindos do backend.
- Adicionar painel de detalhes financeiros.

Dados:

- Comecar com top classes, top fundos, top gestores e sinais de stress.
- Depois adicionar B3 participantes/contratos.
- Depois adicionar ICI paises/regioes.
- Depois adicionar CFTC participantes/contratos.

Controle:

- Nunca carregar todos os fundos de uma vez no grafo visual.
- Usar top N e agregacoes.
- Preservar fonte e data de corte em todo node/edge.
- Toda aresta numerica deve ter atributos auditaveis.

---

## 13. Conclusao

O projeto ja tem dados suficientes para pedir ao analista uma proposta de grafo especifico. O mais importante e decidir se o grafo sera:

- operacional, para investigar fluxo e stress;
- explicativo, para mostrar fontes e relacoes;
- global, para comparar paises/regioes;
- de mercado, para B3 e contratos;
- semantico, para memoria e narrativa.

A infraestrutura existente de grafo e reaproveitavel, principalmente o `GraphPanel.vue`. A melhor decisao tecnica e criar um endpoint proprio do Funds Flow Local que converta dados financeiros ja calculados em nodes/edges, mantendo Graphiti/Zep como camada complementar de memoria e nao como fonte oficial dos numeros.

