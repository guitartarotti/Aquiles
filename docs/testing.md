# Testing and Coverage Policy

Aquiles uses branch coverage and three independent quality gates:

| Scope | Enforced minimum | Target |
| --- | ---: | ---: |
| Backend global | 40% | 45% or higher |
| Critical Funds Flow | 60% | 60% or higher |
| Pure financial calculations | 80% | 80% or higher |
| Authentication | 90% | 90% or higher |

The global threshold is a ratchet: it may increase after measured improvements and must
not be lowered. Large untested modules remain in the denominator; integrations and legacy
services are not excluded simply to improve the reported percentage.

The current full-suite measurement is 40.76% combined branch coverage, with 240 tests.

## Test Layers

- Unit tests cover deterministic financial and normalization rules.
- Property tests use Hypothesis to validate invariants over generated inputs.
- Contract tests freeze request and response expectations for external providers.
- Application tests cover use cases and replaceable ports.
- API and microservice tests protect HTTP payloads and health checks.
- E2E tests cover the primary browser journeys.

Property tests currently protect conservation of subscriptions, redemptions and net flow;
rolling-period sums; bounded ratios; probability normalization; idempotent source
normalization; and correlation/statistical invariants.

External Funds Flow contracts currently cover CVM CKAN, ANBIMA Strapi, B3 listed funds and
ICI publication pages without making network requests during the test suite.

## Real Infrastructure Integration

The CI workflow has a dedicated integration job backed by PostgreSQL 16, Redis 7 and
Neo4j 5 containers. It applies the production PostgreSQL migration and exercises the
Funds Flow repositories, validates an atomic Redis write with expiration, and creates,
queries and removes an isolated Neo4j subgraph through the project driver.

These tests use the `integration` marker and require
`AQUILES_RUN_INTEGRATION_TESTS=1`. The regular unit suite collects them as explicit
skips, keeping local development deterministic when the infrastructure stack is absent.
