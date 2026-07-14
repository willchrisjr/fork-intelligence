# Orchestration

## Lead ownership

The lead agent owns product interpretation, architecture, root manifests,
shared contracts, core entities, security boundaries, integration, validation,
status, and final review.

## Workstreams

| Workstream             | Allowed ownership                              | Depends on                        | Status                        |
| ---------------------- | ---------------------------------------------- | --------------------------------- | ----------------------------- |
| Documentation/research | `docs/research`, architecture and product docs | Approved plan                     | Complete                      |
| Platform               | `services/platform`                            | Root architecture                 | Complete; reviewed            |
| Platform tests         | `tests/platform`, `fixtures/git`               | Stabilized platform interfaces    | Complete; 106 checks          |
| Web                    | `apps/web`                                     | API contracts and design contract | Complete; reviewed            |
| Browser/E2E            | `apps/web/e2e`                                 | Integrated product routes         | Complete; 19 pass             |
| Foundation review      | Read-only repository review                    | Foundation artifacts              | Complete; findings integrated |
| Security review        | Read-only platform/security review             | Integrated platform               | Complete; no P0               |
| Final integration      | Lead-owned                                     | All workstreams                   | Complete                      |

## Coordination rules

- Root manifests, migration head, contracts, core entities, status, decisions,
  and this file have one owner.
- Workstreams return files, interfaces, tests, assumptions, limitations, and
  exact accepted/unmet criteria.
- The lead inspects every diff and reruns relevant checks before integration.
- Model selection is not exposed by the current runtime; bounded mechanical
  tasks receive smaller contexts, while architecture, Git correctness,
  security, and integration stay with the lead or an independent reviewer.

## Final fan-in

The lead inspected shared contracts and delegated outputs, corrected integration
defects found by real data and browser review, regenerated OpenAPI/TypeScript,
reran all relevant checks, exercised an isolated PostgreSQL integration database,
and performed the final Compose/real-repository/browser validation. Delegated
agents did not commit or change shared contracts independently.
