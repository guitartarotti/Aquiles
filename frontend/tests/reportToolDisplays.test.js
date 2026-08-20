import assert from "node:assert/strict";
import test from "node:test";

import {
  getToolColor,
  getToolDisplayName,
  getToolIcon,
  parseInsightForge,
  parseInterview,
  parsePanorama,
  parseQuickSearch,
  renderMarkdown,
} from "../src/components/reportToolDisplays.js";

test("maps known report tools and preserves safe fallbacks", () => {
  assert.equal(getToolDisplayName("insight_forge"), "Deep Insight");
  assert.equal(getToolColor("interview_agents"), "green");
  assert.equal(getToolIcon("quick_search"), "zap");
  assert.equal(getToolDisplayName("custom_tool"), "custom_tool");
  assert.equal(getToolColor("custom_tool"), "gray");
});

test("parses insight counts, entities, and relationship chains", () => {
  const result = parseInsightForge(`
分析问题: Impacto da Selic
预测场景: Juros em alta
相关预测事实: 2条
涉及实体: 1
关系链: 1
### 分析的子问题
1. Como muda o credito?
### 【关键事实】
1. "O custo de capital sobe"
### 【核心实体】
- **Banco Central** (instituicao)
摘要: Define a taxa basica
相关事实: 2
### 【关系链】
- Selic --[pressiona]--> Credito
`);

  assert.equal(result.query, "Impacto da Selic");
  assert.deepEqual(result.stats, { facts: 2, entities: 1, relationships: 1 });
  assert.equal(result.entities[0].name, "Banco Central");
  assert.deepEqual(result.relations[0], {
    source: "Selic",
    relation: "pressiona",
    target: "Credito",
  });
});

test("parses panorama and quick-search result collections", () => {
  const panorama = parsePanorama(`
查询: Inflacao
总节点数: 4
总边数: 3
当前有效事实: 1
历史/过期事实: 1
### 【当前有效事实】
1. IPCA acelerou
### 【历史/过期事实】
1. IPCA desacelerou
### 【涉及实体】
- **IPCA** (indicador)
`);
  const quickSearch = parseQuickSearch(`
搜索查询: cambio
找到 2 条
### 相关边:
- Dolar --[afeta]--> Inflacao
### 相关节点:
- **Dolar** (ativo)
### 相关事实:
1. O dolar subiu
2. A volatilidade aumentou
`);

  assert.equal(panorama.stats.nodes, 4);
  assert.deepEqual(panorama.activeFacts, ["IPCA acelerou"]);
  assert.equal(quickSearch.count, 2);
  assert.equal(quickSearch.edges[0].relation, "afeta");
  assert.equal(quickSearch.facts.length, 2);
});

test("parses interview metadata and renders report markdown", () => {
  const interview = parseInterview(`
**采访主题:** Perspectiva de juros
**采访人数:** 2 / 3 位模拟Agent
### 采访对象选择理由
1. **Analista**: acompanha o mercado
---
### 采访实录
#### 采访 #1: Mercado
**Analista** (economista)
_简介: Especialista em juros_
**Q:** 1. Qual a perspectiva?

**A:** Resposta cautelosa
`);

  assert.equal(interview.topic, "Perspectiva de juros");
  assert.equal(interview.agentCount, "2 / 3");
  assert.equal(interview.interviews[0].name, "Analista");

  const html = renderMarkdown("## Titulo externo\n\n### Cenario\n- **Alta**");
  assert.doesNotMatch(html, /Titulo externo/);
  assert.match(html, /<h4 class="md-h4">Cenario<\/h4>/);
  assert.match(html, /<strong>Alta<\/strong>/);
});
