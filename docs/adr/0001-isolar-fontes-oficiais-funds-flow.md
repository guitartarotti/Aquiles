# ADR 0001: Isolar fontes oficiais do Funds Flow por portas e adaptadores

- **Status**: Aceito
- **Data**: 2026-08-20
- **Decisores**: Equipe Aquiles
- **Contexto**: Funds Flow

## Contexto

O Funds Flow combina informações de CVM, ANBIMA, B3 e Investment Company
Institute (ICI). Essas fontes possuem contratos, frequências de publicação,
formatos, políticas de acesso e estratégias de cache diferentes.

Historicamente, o `FundsFlowLocalService` concentrava orquestração, acesso às
fontes, download, leitura de arquivos, normalização e agregação. Essa concentração
criava os seguintes riscos:

- testes do pipeline dependentes de detalhes privados dos provedores;
- troca de uma fonte pública por API licenciada exigindo alterações no orquestrador;
- tratamento de timeout, cache e falhas misturado às regras financeiras;
- consumidores, como o Radar CDA, chamando métodos privados do serviço;
- crescimento contínuo de um módulo já extenso.

## Decisão

Cada provedor oficial será acessado por uma porta específica da camada de
aplicação:

- `CvmSource`: Informe Diário e cadastro de fundos;
- `AnbimaSource`: consolidado diário, rankings e publicações de fundos;
- `B3Source`: ETFs listados, participantes, open interest e relatórios de mercado;
- `IciSource`: fluxos globais de fundos mútuos e ETFs.

As portas ficam em
`backend/app/domains/funds_flow/application/source_ports.py`. Implementações
concretas ficam nos módulos `*_source.py` de
`backend/app/domains/funds_flow/infrastructure/` e são exportadas diretamente pelo
pacote de infraestrutura.

O `FundsFlowLocalService` coordena somente essas portas. Ele recebe os adaptadores
por injeção de dependência e fornece implementações padrão para preservar os
entrypoints existentes. O Radar CDA usa a porta pública da CVM, sem acessar métodos
privados de coleta.

Cada adaptador encapsula download, cache e parsing do respectivo provedor. Essa
separação não altera as portas, as rotas HTTP nem os modelos de resposta.

## Regras

1. Rotas e casos de uso não importam adaptadores concretos.
2. Domínio financeiro não executa HTTP, leitura de planilhas ou escrita de cache.
3. Cada adaptador declara timeout, cache, origem e instante de captura.
4. Falha em uma fonte complementar deve produzir status rastreável sempre que o
   produto puder continuar; ausência da fonte primária deve falhar explicitamente.
5. Novas APIs licenciadas implementam a porta existente ou justificam sua alteração
   em um novo ADR.
6. Dados brutos permanecem reproduzíveis e separados dos resultados derivados.

## Alternativas consideradas

### Manter todas as integrações no serviço principal

Rejeitada. É simples no curto prazo, mas preserva alto acoplamento, dificulta testes
isolados e torna arriscada qualquer troca de fornecedor.

### Criar uma única interface genérica para todas as fontes

Rejeitada. Um contrato como `load(source_id, options)` esconderia diferenças reais
entre períodos, datasets e tipos de retorno, além de transferir validação para
dicionários sem tipagem.

### Criar um microserviço independente para cada provedor imediatamente

Adiada. O isolamento por portas entrega substituição e testabilidade agora, sem
adicionar quatro processos, filas e contratos de rede antes de haver necessidade
operacional comprovada. Uma futura separação em processos pode reutilizar as mesmas
portas.

## Consequências positivas

- provedores podem ser simulados sem rede nos testes;
- APIs públicas e licenciadas podem coexistir durante uma migração;
- regras financeiras deixam de depender do transporte utilizado;
- Radar CDA e novos consumidores usam contratos públicos estáveis;
- limites arquiteturais podem ser verificados automaticamente;
- falhas e métricas passam a ser atribuídas ao provedor correto.

## Consequências negativas

- há mais interfaces e classes para manter;
- durante a transição, os adaptadores ainda delegam parte da execução aos parsers
  legados;
- alterações em datasets compartilhados exigem coordenação entre porta, adaptador e
  contrato de resposta;
- testes de contrato por provedor tornam-se obrigatórios.

## Plano de migração

1. Manter as portas atuais estáveis e cobertas por testes de contrato.
2. Extrair download e cache da CVM para o adaptador CVM.
3. Extrair publicação e planilhas ANBIMA para o adaptador ANBIMA.
4. Extrair tabelas, relatórios e open interest para o adaptador B3.
5. Extrair downloads semanais, mensais e trimestrais para o adaptador ICI.
6. Remover métodos privados legados depois que nenhum consumidor ou teste depender
   deles.

## Verificação

`backend/tests/test_funds_flow_source_adapters.py` valida os contratos públicos e a
substituição das implementações. `backend/tests/test_domain_boundaries.py` impede o
orquestrador de voltar a chamar diretamente as rotinas privadas das quatro fontes.
