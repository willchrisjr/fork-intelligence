# Analysis Pipeline

Every stage is idempotent, checkpointed, bounded, and observable. A stage commits
its outputs and progress event together. Stage inputs include the configuration
and algorithm bundle versions so incompatible results are never silently reused.

## Stages

1. **Validate** — parse the GitHub locator, reject unsupported hosts/syntax, and
   create a normalized request plus configuration snapshot.
2. **Resolve** — fetch the requested repository, immediate parent, and source;
   establish stable IDs and canonical locators.
3. **Census** — enumerate paginated accessible forks and collect normalized
   metadata with field-level REST/GraphQL provenance.
4. **Shortlist** — deterministically prioritize potential original development
   using unique/default-head signals, recency, releases, adoption, and the user's
   mode. Publish metadata-only results immediately.
5. **Fetch** — update exact namespaced refs in the network bare Git store using
   partial blob filtering and sealed snapshot refs.
6. **Structural analysis** — calculate merge bases, reachability, ahead/behind,
   unique commits, stable patch IDs, patch overlap, and raw/adjusted composition.
7. **Deep analysis** — materialize bounded blobs, classify files, parse supported
   dependency manifests, and construct normalized change features.
8. **Score and classify** — calculate separate, versioned dimensions, confidence,
   data coverage, reason codes, and meaningful-fork classification.
9. **Cluster** — build deterministic feature vectors, perform stable
   agglomerative clustering, and label clusters heuristically from representative
   paths, dependencies, and terms.
10. **Finalize** — seal the run, build overview summaries, and enable JSON, CSV,
    and Markdown exports.

There is no live AI stage in the MVP.

## Shortlisting

Shortlisting is a resource allocation decision, not a quality judgment. The v1
priority vector uses observable signals: default-head differs from source,
recent meaningful activity, release recency, downstream forks/stars, active
branches, and explicit user selection. Rules and weights are versioned. Stable
repository ID breaks ties.

The worker always records:

- all discovered forks and their metadata depth;
- shortlist score and reason codes;
- included/excluded branches and reasons;
- configured and effective caps;
- quota/storage/time pressure that changed the plan.

## Branch selection

Analyze the default branch first, then recently active branches, heads ahead of
upstream, release-linked branches, and open-PR branches. Fetch only exact heads
chosen by the planner. Low-signal branches remain visible as excluded. A branch
head SHA and retrieval time seal the analysis input.

## Equivalence ladder

From strongest to weakest:

1. same commit SHA;
2. same stable patch ID;
3. same normalized combined diff (used cautiously for covered squashes);
4. high normalized-diff similarity;
5. shared changed areas/dependencies/terms;
6. semantically related but technically different.

Only levels 1–3 may be displayed as deterministic equivalence, and each names
its method. Levels 4–6 are similarity or relation, never proof.

## Deterministic clustering

The v1 feature schema combines normalized path tokens, directory and file-type
distributions, dependency additions/removals, bounded commit terms, diff
statistics, source/test/build/deploy composition, patch overlap, and public-API
indicators. Sparse features use TF-IDF-like weighting derived only from the run.

Use average-link agglomerative clustering over cosine distance with a versioned
distance threshold. The input order is stable repository ID; equal distances and
representatives use stable ID tie-breaking. Singletons are valid. Labels are
formed from the highest-weight representative paths, dependencies, and terms and
are explicitly marked heuristic.

## Retry and resume

- Retry transient HTTP and Git transport failures with bounded jittered backoff.
- A rate-limit response commits `partial` status, a `waiting_for_quota` stage,
  and a resume time in the quota snapshot.
- Permanent repository errors create a partial item result and continue.
- Cancellation is cooperative at stage/work-item boundaries.
- Resume validates checkpoint input hashes and reruns only invalid/incomplete
  items; attempts are retained for audit.
- A corrupted Git cache is quarantined and rebuilt from recorded heads.

## Provenance contract

Every result is labeled as GitHub-provided, locally calculated, or heuristic.
Every significant claim resolves to evidence IDs. Scores and clusters include
method version, inputs, missing inputs, confidence, depth, and calculation time.
Exports contain the same disclosures; UI summaries may not suppress them.
