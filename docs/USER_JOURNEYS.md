# User Journeys

## A. Explore a fork ecosystem

**Intent:** understand where meaningful development occurred.

1. User enters `owner/repository`, chooses **Explore ecosystem**, and sees the
   security/privacy and methodology links.
2. Input is normalized; the resolved requested, parent, and source repositories
   are shown before analysis continues.
3. The progress view exposes discovered, shortlisted, structural, and deep counts
   plus quota, caps, warnings, and partial-result access.
4. The leaderboard appears after metadata census. The user filters mirrors,
   classifications, depth, activity, and confidence and changes named rankings.
5. The user switches between lineage and development-direction views. A
   synchronized table exposes the same relationships.
6. Selecting a fork opens evidence, score components, Git relationship, patches,
   composition, dependencies, releases, classification reasons, and limitations.

**Failure/partial path:** malformed input is corrected in place; unavailable or
rate-limited data remains visible with a resume time; cancellation preserves
committed partial results.

## B. Find a maintained successor

**Intent:** identify a credible continuation, not merely the newest push.

1. User chooses **Find maintained successor**.
2. Results rank the named successor profile while retaining separate maintenance,
   sustained activity, releases, contributors, adoption, originality, docs/tests,
   compatibility, and severe-staleness components.
3. Each candidate shows confidence, coverage, missing inputs, depth, and reason
   codes; test/CI presence is described as evidence of practice, not quality.
4. User compares the strongest candidates with upstream and inspects release,
   activity, compatibility, and unmerged-patch evidence.

**Done:** the user can explain why a candidate ranks highly and what evidence or
missing data could change that conclusion.

## C. Compare upstream and forks

**Intent:** choose among concrete variants or estimate integration effort.

1. From the leaderboard or detail page, user selects upstream plus two forks
   (up to three forks may be supported without changing the contract).
2. The comparison view shows selected heads and analysis times, merge bases,
   ahead/behind, unique/shared commits, patch overlap, file/directory composition,
   dependencies, releases, activity, scores, classifications, and change families.
3. Matrix cells distinguish same commit, equivalent patch, similar implementation,
   unique change, absent, and unknown.
4. The integration estimate names its approximation and links to evidence rather
   than implying a dry-run merge occurred.
5. User exports or copies stable GitHub evidence links.

**Staleness path:** if a selected head changed after analysis, the view labels the
snapshot stale and offers a refresh without replacing the old evidence silently.

## D. Find useful unmerged work

**Intent:** discover valuable patches or change families absent upstream.

1. User chooses **Find unmerged innovation**.
2. Pipeline removes shared commits, then deduplicates equal stable patches and
   covered combined-diff equivalents.
3. Remaining changes are grouped deterministically by paths, dependencies,
   composition, terms, and patch overlap.
4. User inspects representative commits/patches/files and compares alternative
   implementations touching the same area.
5. Uncertain similarity is explicitly distinct from deterministic equivalence.

## E. Resume an interrupted analysis

1. User reopens a cancelled, failed-transient, or quota-waiting run.
2. UI shows the last sealed checkpoint, failed items, configuration, and whether
   repository heads have changed.
3. Resume creates a new attempt, reuses valid checkpoints, and reruns only stale
   or incomplete work.
4. Event history preserves both attempts and partial results remain inspectable.

## Cross-journey accessibility

All controls are keyboard reachable, focus returns to affected evidence after a
drawer/filter action, state is not conveyed by color alone, tables describe graph
conclusions, score explanations are available without hover, reduced motion is
honored, and repository/commit/patch identifiers use readable text rather than
rasterized UI.
