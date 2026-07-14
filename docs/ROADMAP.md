# Roadmap

Roadmap items are outcomes, not commitments. Each milestone exits only with its
checks reported and limitations updated.

## M0 — Foundation

- Research, product requirements, threat model, system/data/pipeline design, ADRs.
- Monorepo boundaries, OpenAPI contract, synthetic fixture design, local
  PostgreSQL/Redis workflow.
- Exit: no unresolved architecture/security blocker and source register current.

## M1 — Executable scaffold

- Next.js web, FastAPI API and worker entrypoints, PostgreSQL migrations, Redis
  queue, durable progress/events, health checks, CI and formatting/type/lint/test
  harnesses.
- Exit: clean startup proves web/API/worker/database/queue communication.

## M2 — Public metadata vertical slice

- Safe submission, REST resolution and paginated fork census, anonymous mode,
  optional authenticated GraphQL acceleration, snapshots, progress, quota/error
  states, and evidence table.
- Exit: one real public repository produces a persisted visible census.

## M3 — Git intelligence

- Bare network stores, namespaced refs, branch planner, merge bases,
  ahead/behind, unique commits, stable patch IDs, composition, and actual Git
  fixtures.
- Exit: mirror/divergent and covered rebase/cherry-pick/squash cases are correct.

## M4 — Explainable interpretation

- Raw metrics, separate score dimensions and profiles, confidence/coverage,
  deterministic classifications, reason codes, and detail pages.
- Exit: every score and classification is reproducible and evidence-linked.

## M5 — Comparison, map, and exports

- Upstream-plus-two comparison, overlap/change matrices, lineage map with table
  alternative, JSON/CSV/Markdown exports.
- Exit: users navigate claim to evidence and export the same provenance.

## M6 — Deterministic directions

- Versioned feature vectors, agglomerative clusters, heuristic labels, cluster
  cards, change-family matrix, and method fixtures.
- Exit: membership/labels are stable and explainable without an LLM.

## M7 — Hardening and release readiness

- Browser/accessibility/security review, failure recovery, benchmark fixtures,
  real-repository smoke, deployment/operations runbooks, retention, and
  independent review.
- Exit: end-to-end MVP is usable and validation is reported accurately.

## Near-term after MVP

- Saved/public shareable analyses and incremental refresh.
- More dependency ecosystems and stronger normalized-diff/change-family methods.
- Repository health alerts and upstream absorption tracking.
- GitHub App installation and webhook-driven refresh.

## Intermediate

- Private repositories with tenant isolation and credential lifecycle.
- Scheduled monitoring, security-patch propagation, maintainer workflows, and
  review-only pull-request candidate recommendations.
- Organization dashboards and evidence query interface.
- Consider evidence-grounded AI enrichment only after a new ADR/threat review;
  deterministic behavior remains the fallback.

## Long-term

- Related repositories not declared as forks and cross-forge provenance.
- GitLab and Bitbucket.
- Enterprise internal-fork governance and historical research datasets.
- Review-gated integration assistance; never automatic merge by default.
