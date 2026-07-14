# Fork Intelligence MVP Plan

Status: implemented and validated on 2026-07-13. Deferred items remain listed
below and in `docs/STATUS.md`; they are not required for the single-tenant MVP.

## Product scope

Build a single-tenant web application that accepts a public GitHub repository,
discovers its accessible fork network, progressively shortlists meaningful
forks, performs safe Git analysis, and exposes evidence-backed rankings,
details, comparisons, clusters, and exports.

## First vertical slice

Repository submission -> durable analysis job -> GitHub resolution and fork
census -> persisted partial results -> SSE progress -> sortable fork table.
This path must work against a real public repository before deep Git analysis is
added.

## Architecture and service boundaries

- Next.js owns presentation, URL state, and accessible visualization fallbacks.
- FastAPI owns validation, read models, job control, exports, and OpenAPI.
- Dramatiq workers own network and Git analysis stages.
- PostgreSQL owns durable state, checkpoints, evidence, and progress events.
- Redis transports jobs but is never the only copy of user-visible state.
- A bare per-network Git store owns commit objects and namespaced refs.

## Analysis pipeline

1. Validate input and create an idempotent run.
2. Resolve requested, parent, and source repositories.
3. Census accessible forks with page checkpoints.
4. Shortlist using visible low-cost signals.
5. Fetch selected exact refs into staging, then pin analysis refs.
6. Compute ancestry, unique commits, file composition, and patch evidence.
7. Calculate versioned scores, coverage, confidence, and classifications.
8. Cluster deterministic feature vectors and build comparisons.
9. Generate versioned exports and finalize the run.

## Milestones and acceptance criteria

- M0 foundation — complete: repo instructions, research, ADRs, threat model, contracts,
  Docker infrastructure, CI, and commands are present.
- M1 metadata — complete: a real repository produces progressive persisted census results.
- M2 Git — complete: synthetic histories prove ancestry and patch-equivalence behavior.
- M3 decisions — complete: rankings, classifications, details, comparisons, and exports are
  reproducible and evidence-linked.
- M4 directions — complete: bounded evolution view and deterministic clusters work with an
  accessible table and matrix alternative.
- M5 hardening — complete: clean migrations, retries/resume, tests, browser inspection,
  concept fidelity, performance, and security review pass.

## Risks and deferred features

Primary risks are GitHub quota, incomplete network visibility, large histories,
Git resource abuse, misleading equivalence claims, and heuristic confidence.
Private repositories, non-GitHub forges, monitoring, accounts, multi-tenancy,
live LLM enrichment, advanced semantic equivalence, vulnerability scanning, and
automatic repository mutation are deferred.

## Testing and delegation

Use pure unit tests, recorded GitHub boundary fixtures, real synthetic Git
repositories, PostgreSQL/Redis integration tests, generated-contract drift
tests, Playwright workflows, and one opt-in real-repository smoke test.
Delegated work owns non-overlapping directories and is reviewed and integrated
by the lead agent.
