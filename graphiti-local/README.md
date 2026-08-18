# Graphiti Local Environment

This folder holds an isolated Python environment for Graphiti local experiments.

Why a separate environment:

- `graphiti-core` currently requires `neo4j>=5.26.0`
- the main MiroFish backend depends on `camel-oasis==0.2.5`
- `camel-oasis` pins `neo4j==5.23.0`

Keeping Graphiti isolated avoids breaking the current MiroFish backend while we migrate the graph layer.

## Setup

Create the virtual environment and install dependencies:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Current package set

- `graphiti-core==0.28.2`
- JDK 21 is required for the Neo4j 5.26 LTS local runtime

## Local runtime

The tests in this folder expect:

- a Neo4j 5.26+ local server
- root `.env` populated with `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- root `.env` populated with `LLM_API_KEY` or `OPENAI_API_KEY`

Example Windows startup flow for the extracted Neo4j ZIP:

```powershell
$env:JAVA_HOME='C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
cd ..\.codex-run\neo4j-community-5.26.24
.\bin\neo4j-admin.bat dbms set-initial-password 'your-password'
.\bin\neo4j-admin.bat server console
```

## Test commands

Connection smoke test:

```powershell
.venv\Scripts\python.exe smoke_test.py
```

End-to-end ingest test:

```powershell
.venv\Scripts\python.exe e2e_test.py
```

## Planned use

- local Graphiti experiments
- Neo4j-backed graph backend migration
- OpenAI-based extraction during the migration away from Zep Cloud
