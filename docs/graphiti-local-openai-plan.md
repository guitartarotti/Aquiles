# Graphiti Local + OpenAI Migration Plan

## Goal

Replace the current `zep-cloud` graph dependency with a local Graphiti-based stack while keeping OpenAI as the LLM provider.

## Why

The current backend depends on Zep Cloud for:

- graph creation
- ontology registration
- text batch ingestion
- graph search and paging

This creates a hard dependency on `ZEP_API_KEY` and blocks local-first deployment.

## Current Coupling Points

- `backend/app/services/graph_builder.py`
  - creates graphs via `zep_cloud`
  - sets ontology through Zep SDK types
  - ingests text chunks as Zep episodes
  - reads graph data through Zep paging helpers
- `backend/app/services/zep_tools.py`
  - report/search tools read facts, nodes, and edges directly from Zep
- `backend/app/utils/zep_paging.py`
  - pagination helper specialized for Zep node/edge APIs
- `backend/requirements.txt`
  - includes `zep-cloud`

## Target Infra

### Minimum local stack

- `Aquiles backend`
- `Graphiti core`
- `Neo4j 5.26+`
- `OpenAI API key`

### Optional later

- `Ollama` for local LLM inference
- `FalkorDB` instead of Neo4j
- Docker Compose for one-command local startup

## Environment Needed

### Backend

- `LLM_API_KEY`
- `LLM_BASE_URL=https://api.openai.com/v1`
- `LLM_MODEL_NAME=gpt-4o-mini`

### Neo4j

- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=<password>`

### New graph backend selector

- `GRAPH_BACKEND=graphiti_local`

## Recommended Local Infra

### 1. Neo4j

Run locally with Docker:

```bash
docker run --name miro-neo4j ^
  -p 7474:7474 -p 7687:7687 ^
  -e NEO4J_AUTH=neo4j/password ^
  neo4j:5.26
```

### 2. Python dependencies

Expected additions:

- `graphiti-core`
- Neo4j driver if not already brought by Graphiti

### 3. OpenAI

Use a standard OpenAI project key for:

- extraction / structured output
- reranking if needed by the Graphiti integration path
- any scenario generation still handled by Aquiles

## Migration Strategy

### Phase 1. Abstraction layer

Create a graph backend interface with operations for:

- create graph
- set ontology
- add text batches
- wait for ingestion
- get graph data
- search facts
- search nodes
- search edges

Keep the existing Zep implementation behind this interface first.

### Phase 2. Graphiti local backend

Implement a `GraphitiLocalBackend` using:

- Graphiti core
- Neo4j local
- OpenAI client

This backend should accept the same ontology/text inputs already produced by Aquiles.

### Phase 3. Tool migration

Replace direct `zep_tools` reads with a backend-agnostic search service.

Target outputs to preserve:

- facts
- nodes
- edges
- relationship chains
- temporal context

### Phase 4. Runtime switch

Select backend by env:

- `GRAPH_BACKEND=zep_cloud`
- `GRAPH_BACKEND=graphiti_local`

This lets us migrate incrementally and keep rollback simple.

## Technical Risks

### 1. Ontology mismatch

The current ontology path is built around Zep SDK entity and edge models.
Graphiti local may require a different mapping for schema definition and ingestion.

### 2. Search parity

`zep_tools.py` assumes Zep-style facts/nodes/edges. We will need an adapter so report generation keeps the same data contract.

### 3. Market fit

Even after migration, this graph layer is best used for:

- context
- event linkage
- temporal memory
- scenario explanation

It is not the ideal primary engine for:

- market microstructure
- short-horizon forecasting
- latency-sensitive execution

## Recommended Sequence For This Repo

1. Introduce graph backend interface without behavior change.
2. Move Zep-specific calls behind the interface.
3. Add Graphiti local backend skeleton and config.
4. Switch graph build to the backend selector.
5. Migrate report/search tools off direct Zep calls.
6. Test macro snapshot -> project sync -> graph build on Neo4j.

## Decision

Preferred path for this project:

- Graph backend: `Graphiti local`
- Database: `Neo4j`
- LLM: `OpenAI`

This is the lowest-risk route to eliminate Zep Cloud while keeping output quality stable.
