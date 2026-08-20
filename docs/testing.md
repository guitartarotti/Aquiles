# Testing and Coverage Policy

Aquiles uses branch coverage and three independent quality gates:

| Scope | Enforced minimum | Target |
| --- | ---: | ---: |
| Backend global | 31% | 40% |
| Critical Funds Flow | 60% | 60% or higher |
| Pure financial calculations | 80% | 80% or higher |
| Authentication | 90% | 90% or higher |

The global threshold is a ratchet: it may increase after measured improvements and must
not be lowered. Large untested modules remain in the denominator; integrations and legacy
services are not excluded simply to improve the reported percentage.

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
