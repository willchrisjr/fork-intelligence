# Branch coverage benchmarks

Benchmark record for the analysis-coverage release: structural branch coverage,
provider quota consumption, stage latency, and Git storage use on real public
fork networks, measured against the prior default-branch-only baseline.

Following the standard set in [PERFORMANCE.md](./PERFORMANCE.md), **no result is
claimed here until a command, environment, sample count, and raw output are
recorded.** This page currently records a readiness assessment and one measured
limit; the coverage measurements themselves are outstanding.

## Status

**Not yet measured — blocked on provider access.** See
[Blocking condition](#blocking-condition). The harness, methodology, and
environment are ready; the run is roughly an hour of wall time once unblocked.

## Blocking condition

Two conditions prevent the benchmark from running. Both are GitHub account
state, not code.

### No operator credential is configured

`Settings.github_token` resolves to `None` — no `.env` exists at the repository
root or in `services/platform`. Authenticated-mode analyses cannot be started,
so the authenticated half of the comparison cannot be produced.

### Anonymous quota is smaller than one analysis

Measured on the benchmark host, 2026-07-29:

```
$ curl -s https://api.github.com/rate_limit
core: 60/60 per hour
```

One complete analysis costs substantially more than that. Derived from the
release's own configured caps rather than from a trial run:

| Stage | REST requests | Source |
| --- | --- | --- |
| Resolution | 1–2 | one `get_repository`, plus one more when the requested repository is itself a fork |
| Census | up to 45 anonymous / 100 authenticated | `max_github_requests`, capped to 45 in anonymous mode |
| **Branch planning** | **up to 143** | (root + `max_deep_repositories` = 13 repositories) × (1 `list_branches` + up to `max_branch_probes` = 10 `compare_commits`) |
| Structural | 1+ | `get_branch` for the root; Git object fetches do not consume REST quota |

Branch planning alone can require ~143 requests against a 60/hour ceiling.

**This is a genuine observed limit, not a defect.** An anonymous analysis of a
medium or large network will exhaust quota mid-planning and degrade to a partial
result with a `provider_access_exhausted` condition — the behavior
REQ-RA-AGA-002 specifies. The product is correct; the benchmark simply cannot
obtain complete anonymous coverage figures for networks of the size this work
order targets.

Authenticated access (5,000 requests/hour) absorbs roughly 25–30 complete
analyses per hour, which covers the full matrix below comfortably.

### Implication for benchmark design

Anonymous-mode figures for medium and large networks will necessarily describe a
**partial** analysis. That is worth measuring — it is the honest anonymous
experience — but it must be reported as partial coverage against a quota
ceiling, never presented as the release's coverage capability.

## Environment

Recorded so a later run is comparable.

| Property | Value |
| --- | --- |
| Repository commit | `5c2fd49` |
| Assessed | 2026-07-29 |
| Python | 3.14.6 |
| Node | 26.5.0 |
| PostgreSQL | 17.10 (schema migrated) |
| Redis | reachable |
| Branch planner version | `2026.07.2` |
| Anonymous GitHub quota | 60/hour |

Effective caps at time of assessment: `max_forks` 250, `max_github_pages` 5,
`max_github_requests` 100, `max_shortlist` 12, `max_deep_repositories` 12,
`max_branches_per_fork` 3, `max_branch_candidates` 50, `max_branch_probes` 10.

## Methodology

### Repository selection

Choose public repositories by **accessible fork count**, avoiding networks so
large that `max_forks` dominates the result:

- **Medium:** 50–250 accessible forks, several forks with non-default branches.
- **Large:** 1,000+ accessible forks, to exercise `max_forks` and page caps.

Record the selection and each repository's fork count at run time; fork counts
move, and a result is only interpretable against the count observed that day.

### Run matrix

Five complete analyses:

| # | Network | Mode | Purpose |
| --- | --- | --- | --- |
| 1 | Medium | Authenticated | Primary coverage measurement |
| 2 | Medium | Anonymous | Fallback coverage and quota behavior |
| 3 | Large | Authenticated | Cap and scale behavior |
| 4 | Large | Anonymous | Fallback under scale |
| 5 | Medium | Authenticated, repeat | Reproducibility on unchanged heads |

Run 5 must follow run 1 closely enough that heads have not moved. If any head
has moved, WO-8 re-validation will correctly re-plan that repository — record
that as a re-plan rather than a reproducibility failure, and repeat.

### Measurements

Per analysis, all available from delivered disclosures — no instrumentation
needed:

- **Branch coverage** — `branch_plan.counts`: considered, selected,
  `excluded_by_cap`, `unevaluated`, `structurally_analyzed`. Available on
  `GET /api/v1/analyses/{id}` and in JSON exports.
- **Credential mode history** — `access.credential_mode`,
  `access.transitions`, `access.coverage_limitations`.
- **Quota consumption** — `access.quota` at completion, against a
  `/rate_limit` reading taken immediately before the run.
- **Stage latency** — `ProgressEvent` rows: `stage.started` to
  `stage.completed` per stage, from `GET /api/v1/analyses/{id}/events`.
- **Git storage** — `du -sh` of `git_store_root` before and after.
- **Baseline delta** — structural coverage against default-branch-only. The
  baseline is `branches_structurally_analyzed` where every selected branch is a
  default: equivalently, one branch per structurally analyzed repository. The
  delta is the release's primary success measure.

### Reproducibility check

For run 5, compare the persisted branch plans, not the rendered response:

```sql
SELECT repository_id, name, decision, priority, selection_reason, head_sha
FROM branches WHERE analysis_id = '<run-5-id>' ORDER BY repository_id, priority;
```

Identical ordering, decisions, reasons, and heads against run 1 confirms
AC-RA-RBP-003.1. A difference is only acceptable where an observed head moved,
which the WO-8 revalidation summary in `sampling.branch_plan_revalidation` will
name explicitly.

## Running the benchmark

Once an operator credential is configured:

```bash
pnpm infra:up
pnpm db:migrate
pnpm dev            # or run the API and worker separately
```

Start an analysis and follow it to completion:

```bash
curl -s -X POST localhost:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: bench-$(date +%s)" \
  -d '{"repository":"<owner>/<name>","mode":"explore"}'

curl -s localhost:8000/api/v1/analyses/<id> | jq '{access, branch_plan, sampling}'
curl -s localhost:8000/api/v1/analyses/<id>/exports/json > bench-<id>.json
```

For the anonymous run, start the worker with no credential in its environment;
the router reports `credential_mode: anonymous` and records the reason.

Record raw output alongside each result in this document. Per the standard in
PERFORMANCE.md, a summarized figure without its raw output is not a benchmark.

## Results

None recorded. This section is intentionally empty rather than populated with
estimates: a projected coverage number would be indistinguishable from a
measured one once it is quoted elsewhere.
