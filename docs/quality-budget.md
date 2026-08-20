# Quality Budget

Aquiles uses a ratcheting quality budget to prevent architectural and maintenance
regressions while legacy modules are decomposed gradually.

Run the gate locally from the repository root:

```bash
npm run quality:budget
```

The budget enforces:

- default size limits of 800 lines for backend Python modules and 500 lines for
  frontend JavaScript, TypeScript, and Vue modules;
- explicit ceilings for existing oversized modules;
- ceilings for `type: ignore`, `noqa`, and owned frontend `eslint-disable` comments;
- no unapproved backend dependency cycles;
- no domain-layer imports from infrastructure;
- no direct `fetch` or Axios transport calls in frontend components;
- the global and critical coverage floors declared in the CI workflow.

The source of truth is [`quality-budget.toml`](../quality-budget.toml). Existing
oversized files are listed individually, so a new file cannot inherit a legacy
exception.

## Ratchet Policy

Do not raise a limit only to make CI pass. A budget increase requires an explicit
technical justification in the pull request and should be exceptional. When a
module or suppression count decreases, lower or remove its allowance so the
improvement cannot be reversed later.

New dependency-cycle baselines are not accepted. Remove the cycle or introduce a
port, contract, event, or dependency-injection boundary instead.
