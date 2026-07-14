# Roadmap

The single-tenant public-repository MVP is complete. The items below improve
coverage, resilience, or deployment scope; they are not hidden blockers in the
current end-to-end workflow.

## Priority 1 — Increase analysis coverage

1. Configure a scoped server-side GitHub credential and implement the optional
   GraphQL metadata accelerator with REST fallback, partial-error handling, cost
   budgeting, and contract fixtures.
2. Implement the three-branch planner described in the architecture: default
   branch first, then recently active and meaningfully ahead branches within the
   configured cap.
3. Complete bounded blob hydration for deep analyses so more shortlisted commits
   receive patch fingerprints, file categories, and dependency evidence instead
   of an explicit `missing_blobs` result.
4. Exercise these changes on medium and large real fork networks and publish
   updated quota, latency, disk, and evidence-coverage benchmarks.

Exit criteria: authenticated mode materially increases accessible coverage;
REST-only mode remains correct; branch selection is visible and reproducible;
and deep-analysis evidence coverage improves without weakening resource limits.

## Priority 2 — Automate operations and recovery

1. Add the scheduled retention job for expired analyses, exports, and
   unreferenced Git stores with dry-run, audit counts, and active-run protection.
2. Add periodic reconciliation for durable queued/running work after broker or
   worker interruption, building on the existing idempotent manual resume path.
3. Ship metrics, structured operational events, dashboards, and alerts for queue
   age, stage latency, GitHub quota, Git failures, disk watermarks, and SSE lag.
4. Automate PostgreSQL backup/restore drills and document recovery objectives.

Exit criteria: cleanup and reconciliation are safe under fault injection;
operators can detect stalled or capacity-limited analyses; and a clean restore
recovers durable analyses, evidence, and ordered events.

## Priority 3 — Improve the investigator workflow

1. Add saved/shareable analysis labels and incremental refresh while preserving
   immutable historical snapshots.
2. Add repository-health alerts and upstream-absorption tracking for valuable
   patches that later appear upstream.
3. Expand dependency ecosystems and strengthen normalized-diff and change-family
   methods with new deterministic fixtures.
4. Add comparison annotations and maintainer-oriented evidence queues without
   mutating upstream repositories.

Exit criteria: refreshed results remain provenance-safe, notifications link to
new evidence, and every new interpretation has deterministic fallback behavior.

## Priority 4 — Prepare for public or multi-tenant deployment

1. Add authentication, tenant authorization, per-tenant quotas, audit logs, and
   credential lifecycle management.
2. Add GitHub App installation, signed webhook ingestion, delivery
   deduplication, and private-repository support.
3. Add edge abuse controls, TLS/private service networking, encrypted backups,
   deployment-specific secrets management, and an external operational security
   review.

Exit criteria: private data cannot cross tenants; credentials are scoped and
rotatable; webhook replay is safe; and the deployment threat model and recovery
plan pass independent review.

## Later exploration

- Evidence-grounded AI summaries after a new ADR and prompt-injection review;
  deterministic analysis remains authoritative and usable without an AI key.
- Related repositories that are not declared GitHub forks and cross-forge
  provenance for GitLab and Bitbucket.
- Organization dashboards, historical research datasets, and review-gated
  integration recommendations. Automatic merge remains out of scope.
