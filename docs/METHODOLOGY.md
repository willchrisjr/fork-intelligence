# Methodology

## Evidence before interpretation

Fork Intelligence models repository metadata, commit graphs, patch equivalence,
and change families separately. Each result is tagged as:

- **Provider fact:** returned by GitHub with endpoint/version/retrieval time.
- **Calculated:** reproduced from sealed Git heads and a named algorithm.
- **Heuristic:** a cautious interpretation with reasons and evidence IDs.

No live AI is used in the MVP. Repository text is never an instruction.

## Analysis depth and sampling

Metadata depth covers the accessible census. Structural depth covers shortlisted
branch heads and computes Git relationships. Deep depth materializes bounded file
content for composition, dependencies, similarity, and clusters. Every run lists
effective caps, shortlist reasons, included/excluded branches, depth per fork,
quota interruptions, and missing data. "All forks" means all accessible records
observed under those disclosures, never hidden/deleted/private repositories.

## Meaningful development

The v1 classification rule bundle considers unique commits/patches, adjusted
source/test changes, patch overlap with upstream, active branches, releases,
recency/continuity, and upstream synchronization. It produces one of mirror or
synchronized, contribution, experimental, specialized variant, patch or
compatibility fork, maintained continuation, independent product direction, or
unknown/insufficient evidence.

Each result includes confidence, ordered reason codes, evidence, missing inputs,
depth, and classifier version. Classification is descriptive, not a quality
grade.

## Patch equivalence

Same SHA is commit identity. Equal `git patch-id --stable` is deterministic
likely patch equivalence across common rebases/cherry-picks; the Git/diff version
and parent policy are stored. Covered squashes may compare a bounded combined
normalized diff. High normalized-diff similarity, shared paths, or shared terms
are labeled similarity, not equivalence. No language model can promote a weak
relation into deterministic equivalence.

## File composition

Paths are classified into application source, tests, docs, CI/automation,
build/packaging, dependency manifests, lockfiles, configuration, generated,
vendored, assets, examples, and unknown. Rules are ordered and versioned; users
can inspect classifications. Raw divergence includes every change. Adjusted
divergence discounts generated, vendored, lockfile, and asset churn using visible
weights while preserving raw totals and exclusions.

## Scores

All scores are 0–100, versioned, deterministic, and calculated from separately
stored raw metrics. Each metric is normalized by a published bounded function;
missing inputs are omitted and reduce coverage rather than silently becoming
zero. A profile value is:

```text
score = sum(available_weight_i * normalized_metric_i)
        / sum(available_weight_i)
coverage = sum(available_weight_i) / sum(all_weight_i)
```

Confidence is a distinct 0–1 product of coverage, depth reliability, provenance
quality, and snapshot freshness, using a versioned formula. A high score with low
confidence is visibly low-confidence.

Separate dimensions cover popularity, recent activity, sustained activity,
maintenance, original development, divergence, adoption, upstream compatibility,
maintained-successor likelihood, and unmerged-innovation relevance. Named
profiles publish complete weights. Popularity never proves quality; CI/test
presence never proves correctness; divergence is neither praise nor penalty by
itself.

Activity recency uses time decay rather than a latest-push threshold. The target
v1 decay primitive is `exp(-ln(2) * days / half_life_days)` with the half-life
stored in the method bundle. Continuity uses active time buckets, not total commit
count alone.

## Clustering

Fork vectors use normalized changed-path tokens, directory/file-type
distribution, dependency changes, bounded commit terms, diff statistics,
source/test/build/deploy composition, patch overlap, and public-API indicators.
Average-link agglomerative clustering over cosine distance uses a published
threshold and stable ID tie-breaks. Singletons are allowed. Labels come from
representative high-weight paths, dependencies, and terms and are marked
heuristic. The feature schema, threshold, member evidence, algorithm version,
label method, and confidence are visible.

## Comparisons and integration estimates

Pairwise comparison is bound to explicit heads and shows merge base, ahead/
behind, unique/shared commits, equivalence/similarity levels, file/dependency
composition, releases, activity, scores, and classifications. Integration
complexity is a labeled approximation from structural divergence, patch overlap,
touching changes, API/dependency changes, and behind count. It is not a merge
trial and never promises conflict-free integration.

## Versioning and reproducibility

An analysis records GitHub API version, retrieval validators/times, exact head
SHAs, Git version/options, configuration, metric normalizers, score/classifier/
cluster/file-rule versions, and export schema. Re-running identical sealed inputs
with the same bundle must produce identical deterministic results. Method changes
create new snapshots; historical conclusions are not rewritten.

## Limitations

Accessible API data can be incomplete or stale. Default branches can omit work.
Rename and conflict estimates are heuristic. Patch IDs miss some squashes and
similar independent implementations. Contributor counts and issue responsiveness
can be misleading. Dependency parsing is ecosystem-limited. Repository deletion,
transfer, archived status, Git LFS, very large histories, and API limits may
reduce depth. These limitations appear in UI and exports, not only here.
