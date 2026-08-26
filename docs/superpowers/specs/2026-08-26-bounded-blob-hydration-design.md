# WO-12 — Bounded explicit blob hydration

Date: 2026-08-26
Roadmap: Priority 1, item 3
Work order source: `docs/HANDOFF.md` § "3. Bounded explicit blob hydration"
Scope: `services/platform` only, plus additive contract counters

## Problem

`BareNetworkStore.fetch_branch` performs two fetches. The first,
`--filter=blob:none`, is authoritative and retrieves full ancestry with no blob
content. The second, `--filter=blob:limit=<max_blob_bytes>`, is best effort: it
pulls every under-cap blob in the entire branch history and swallows its own
failures unless a resource or store limit is hit.

`BareNetworkStore.compare` then computes the bounded shortlist — `unique` and
`upstream_unique`, each capped at `max_git_commits` — and calls `patch_id` per
commit. Commits whose blobs are absent raise `git_failed` and are recorded in
`missing_blob_commits`.

The blanket fetch is simultaneously too broad and too narrow:

- **Too broad.** It retrieves blobs for the whole branch history, including
  commits that the shortlist will never reach, so disk use is unrelated to what
  is actually analyzed.
- **Too narrow.** It can abort against the store limit partway through, and
  because it swallows failures, the abort is silent. Blobs the shortlist needs
  may never arrive.

The root cause is ordering. The shortlist that determines which blobs matter is
not computed until `compare`, which runs after the fetch that was supposed to
retrieve them.

## Constraints that shape the design

These are existing decisions, not new choices. They rule out otherwise
reasonable approaches.

- **`GIT_NO_LAZY_FETCH=1`** is set in `SafeGit.run`'s sterile environment,
  alongside `core.hooksPath=/dev/null`, `protocol.ext.allow=never`,
  `protocol.file.allow=never`, and `fetch.fsckObjects=true`. Lazy fetching would
  let an ordinary local Git command open a network connection that is unbounded,
  outside the deadline and store-limit accounting, and triggered by the shape of
  analyzed repository content. **Configuring a promisor remote is therefore not
  available to this design.** Every network operation must remain explicit.
- The store is `git init --bare` with no named remote. All fetches are by URL
  with explicit refspecs, against the allowlisted HTTPS GitHub origin.
- D005 (bounded analysis) requires that every cap or incomplete stage is
  disclosed. `patch_overlap.method` is a versioned string so results are
  reproducible; anything that changes which evidence is produced must be
  reproducible and disclosed too.
- Analyzed repository content is never executed. Fetching Git objects is not
  execution and stays inside the boundary.

## Blob working set

Not every consumer in `compare` needs the same objects. A two-point diff never
needs the commits between the points.

| Consumer | Objects required |
| --- | --- |
| `patch_id(commit)` — `git show --binary` | each shortlisted commit and its parent |
| `range_patch_id` (×2) — `git diff --binary base tip` | endpoint trees only |
| `diff --name-status --find-renames` | the same endpoint trees; rename similarity reads content |
| `diff --name-only merge_base upstream_ref` | none; paths only |

The hydration set is therefore **endpoints plus shortlisted commits and their
parents**, which is enumerable and boundable.

`range_patch_id` already degrades to `None` on `git_failed`. `patch_id` does
not, which is why its failures become `missing_blob_commits`.

## Architecture

Three additions to `adapters/git.py`, one wiring change in
`services/pipeline.py`.

### `BlobHydrationPlan`

A dataclass holding the three endpoint refs, the ordered list of shortlisted
commits, and the enumerated absent-object set with sizes. Produced locally with
no network access.

### `BareNetworkStore.plan_blob_hydration(upstream_ref, fork_ref, *, deadline)`

Pure local. Computes `merge_base`, re-runs the same bounded
`rev-list --reverse --max-count=max_git_commits` that `compare` uses, and
enumerates which required objects are absent. Returns a `BlobHydrationPlan`.

The duplicated `rev-list` is deliberate. It costs one cheap local command and
buys keeping `compare` free of network I/O.

### `BareNetworkStore.hydrate_blobs(plan, identifier, *, deadline)`

The only network step. Walks the plan in order under the budget and returns a
reason-coded outcome per commit.

### `compare` stays local, gains one optional argument

`compare` builds the `patch_overlap.coverage` object, so hydration outcomes have
to reach it in order to be disclosed. It therefore gains a single optional
parameter:

```python
def compare(
    self,
    upstream_ref: str,
    fork_ref: str,
    *,
    timeout: float | None = None,
    hydration: HydrationOutcome | None = None,   # new
) -> HistoryComparison
```

The default of `None` means every existing call site and every offline fixture
test keeps working unchanged, and `coverage.hydration` is omitted when no
hydration was performed. `compare` performs no network I/O in either case — it
receives an already-completed outcome rather than triggering one. That
separation was the deciding reason for placing hydration in the pipeline rather
than inside `compare`.

## Fetch mechanism

**Batched fetch of explicit commit SHAs with `--filter=blob:limit=<max_blob_bytes>`.**

Selected because:

- It is the only candidate proven against this codebase's constraints.
  `fetch_branch` already fetches by URL with a `--filter` under the sterile
  config, in production, passing CI.
- Transfer cost is acceptable. Git negotiates against objects already present,
  so the first commit costs roughly one tree snapshot and each subsequent commit
  transfers only objects not already local — approximately its own changed
  blobs. Total transfer is one snapshot plus the union of changed blobs across
  the shortlist, scoped to the analyzed range rather than all history.

Rejected alternatives:

- **Promisor remote with lazy fetch.** Ruled out by `GIT_NO_LAZY_FETCH=1`; see
  Constraints.
- **Fetching bare blob SHAs.** Tighter in principle, since the exact blob set is
  computable locally from trees via `diff-tree -r`. Depends on server-side
  `uploadpack.allowAnySHA1InWant` for non-commit objects, which is not
  established for GitHub. Marginal gain, real risk.
- **`--filter=sparse:oid` scoped to changed paths.** Most precise, but GitHub's
  support for sparse filters is not established.

### Implementation step zero: mechanism measurement

Before writing production code, run a throwaway spike against a public
repository: fetch `blob:none`, then fetch explicit commit SHAs with
`blob:limit`, and measure what actually transfers.

It answers exactly two questions:

1. Does GitHub honour `blob:limit` on explicit commit-SHA wants?
2. What is the real transfer size for a representative fork shortlist?

The second number is what the budget defaults are set from. If question 1
answers no, the fallback is the blanket-fetch behaviour retained but scoped to
the shortlist range rather than the whole branch, and the spec is revised before
implementation continues.

## Data flow

```
fetch_branch                    blob:none only; blanket blob:limit fetch removed
  -> plan_blob_hydration        local: merge_base, shortlist, absent objects
  -> hydrate_blobs              network: endpoints first, then commits in order
  -> compare(hydration=outcome) local; hydration outcome passed in, not triggered
```

Endpoints are hydrated first because they serve `--find-renames` and both
`range_patch_id` calls. Losing them degrades every fork; losing a tail commit
degrades one fingerprint.

## Ordering and determinism

On budget exhaustion, hydration produces a **deterministic ordered prefix**:
endpoints, then shortlisted commits in the existing `rev-list --reverse`
(oldest-first) order, stopping at the budget. The same repository under the same
caps yields the same hydrated set on every run.

Oldest-first is chosen over newest-first so that the hydrated set shares an
order with the shortlist that `compare` already reports. A different order would
be a subtle trap for anyone reading the evidence. The cost is accepted: when the
budget binds, the newest unique commits are the ones dropped.

## Removing the blanket fetch

The best-effort `--filter=blob:limit` fetch in `fetch_branch` is removed
entirely.

The decisive reason is starvation, not waste. While it remains, irrelevant
whole-history blobs can trip `_enforce_store_limit` and quarantine the store
*before* hydration runs, so the targeted step can be starved by the untargeted
one. Keeping both would leave the failure mode this work order exists to fix.

The risk is that any blob requirement not enumerated in the working-set table
becomes a live failure rather than a silently-masked one. Fixtures covering
renames and aggregate patch IDs address this directly.

## Disclosure

`patch_overlap.coverage` gains a `hydration` object alongside the existing
counters. Additive only.

```
coverage: {
  commit_patches_available,          # existing, unchanged
  commit_patches_missing,            # existing, unchanged
  hydration: {
    method: "bounded-explicit-hydration-v1",
    planned,
    hydrated,
    cutoff_index,                    # 0-based index into the ordered shortlist of
                                     # the first commit NOT hydrated; null when the
                                     # full plan completed
    missing: {
      oversized,                     # exceeds max_blob_bytes
      absent_upstream,               # not served by the remote
      budget_exhausted,              # per-fork or store ceiling reached
      fetch_failed                   # transport or fsck failure
    }
  }
}
```

`missing_blob_commits` keeps its current shape and meaning, so existing
consumers — the WO-6 web disclosures and WO-7 export provenance — continue to
work unchanged while gaining detail.

The versioned `method` string carries the reproducibility claim, matching the
existing `stable-patch-id-and-range-patch-id-v1` convention.

## Budgets and failure handling

Reuses `max_blob_bytes` (per blob), the existing store cap via
`_enforce_store_limit`, `max_analysis_seconds` (deadline), and
`git_timeout_seconds` (per command).

Adds one setting, **`max_hydration_bytes`**, a per-fork ceiling. The store cap
is per-network and shared across every fork in an analysis; without a per-fork
ceiling the first fork analyzed can consume the entire budget and starve the
rest.

Failure policy: every hydration failure is non-fatal and reason-coded.
Hydration does not raise past `git_store_limit` and `git_timeout`, which keep
their current escalating behaviour including store quarantine. A commit whose
blobs do not arrive is recorded as missing. Patch evidence is never fabricated
for unhydrated content.

## Testing

Synthetic fixtures in `fixtures/git/build_fixture.py`, per the work order's
acceptance criteria:

- absent blobs
- oversized blobs (exceeding `max_blob_bytes`)
- binary files
- renames (guards the endpoint-hydration requirement for `--find-renames`)
- partial fetch failure
- corrupt objects (guards `fetch.fsckObjects=true` behaviour)
- successful resume after interruption

Plus one fixture pinning the determinism claim: the same fixture under the same
caps, run twice, must produce an identical hydrated set and an identical
`cutoff_index`.

Platform tests extend `tests/platform/test_git_analysis.py`. `compare`'s
existing offline fixture tests must continue to pass unchanged, which is the
regression guard for the "compare stays local" decision.

## Acceptance criteria

Taken from `docs/HANDOFF.md` § 3, with this design's additions:

- Authoritative ancestry remains full-depth and blob-filtered; no shallow clone
  is substituted.
- Only the blobs needed for endpoints and the bounded shortlist are hydrated.
- Hydration uses validated fixed Git argument arrays and the allowlisted HTTPS
  GitHub origin.
- Per-blob, per-fork, aggregate-store, command-output, and deadline limits are
  enforced.
- An explicit missing-blob result is preserved for oversized, absent, or failed
  hydration; patch evidence is never fabricated.
- Patch IDs and file/dependency evidence are recomputed only for successfully
  hydrated content.
- Patch coverage improves on the capped real smoke without weakening resource
  limits or executing repository content.
- The hydrated set is reproducible under identical inputs and caps.

## Out of scope

- Web presentation of hydration disclosures (follow-on work order).
- Export provenance for hydration outcomes (follow-on work order).
- Real-network coverage benchmarks, which are the separate Priority 1 item 4.
