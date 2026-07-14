# Performance

No benchmark result is claimed until a command, environment, fixture revision,
sample count, and raw output are recorded here. Current status: benchmark targets
and harness requirements defined; measurements pending implementation.

## Service objectives for the MVP

These are initial engineering targets, not validated production guarantees:

| Operation                         | Target                                                                      |
| --------------------------------- | --------------------------------------------------------------------------- |
| Health/read-only metadata API     | p95 under 300 ms excluding cold start                                       |
| Analysis creation acknowledgment  | p95 under 500 ms, job work excluded                                         |
| SSE event visibility after commit | p95 under 2 s                                                               |
| First census partial result       | under 15 s for a small cached network                                       |
| Cached overview/fork page         | p95 under 500 ms                                                            |
| Cancellation recognition          | next safe work boundary, target under 5 s                                   |
| Worker memory/disk                | bounded by configured admission limits; no unbounded clone/output buffering |

Analysis completion time depends on network/history size and GitHub quota, so the
product reports stage progress and depth instead of a universal latency promise.

## Architecture levers

- Census broadly, shortlist deterministically, and deepen selectively.
- Reuse one bare object store per network and cache by stable repository/head IDs.
- Fetch `blob:none` and materialize bounded blobs only for deep analysis.
- Cache API responses with ETags and calculations by sealed SHAs, configuration,
  and algorithm version.
- Use PostgreSQL indexes for run/event sequence, repository identity, snapshot,
  score dimension, and comparison lookups.
- Bound GitHub/Git concurrency; more parallelism can trigger secondary limits or
  increase pack/object contention.
- Generate exports asynchronously from sealed snapshots.

## Deterministic benchmark fixtures

The fixture generator must create real local Git histories for:

- small network baseline;
- medium network;
- many mirror forks;
- many branches;
- rebased equivalent patches;
- squashed patches;
- generated-file-heavy fork;
- vendored-dependency-heavy fork.

Also retain correctness fixtures for cherry-pick, merge, rename, behind/ahead,
divergence, multiple active branches, and independent similar implementations.

## Measurements

For each fixture record commit/fork/branch/object/blob counts, Git and host
versions, cold/warm cache, wall time by stage, CPU, peak RSS, disk before/after,
network/API calls where applicable, cache-hit ratio, DB query count/slow queries,
and output counts. Run at least five measured iterations after warm-up; report
median and p95 without discarding failures.

Recommended benchmark groups:

```text
metadata census
bare fetch and ref update
merge-base/reachability
stable patch fingerprinting
composition/dependency parsing
scoring and clustering
API pagination and SSE replay
JSON/CSV/Markdown export
```

## Guardrails

Regression thresholds belong in versioned benchmark configuration. Correctness
precedes speed: do not use shallow history for structural claims, skip evidence,
or hide sampling. A performance change must preserve deterministic outputs on
the fixture suite. Before raising any cap, test worst-case disk recovery,
cancellation, and concurrent-network behavior.

## Results log

| Date       | Revision     | Environment                   | Fixture                        | Result                                                                             | Status     |
| ---------- | ------------ | ----------------------------- | ------------------------------ | ---------------------------------------------------------------------------------- | ---------- |
| 2026-07-13 | working tree | macOS/Colima, cold API worker | `octocat/Hello-World`, cap 3/2 | completed structural run in about 5.5 s; 3 forks censused, 2 structurally analyzed | smoke only |

This smoke is not the five-iteration deterministic benchmark required for a
performance claim; it demonstrates that the bounded end-to-end path meets the
small-network first-result objective in the current environment.
