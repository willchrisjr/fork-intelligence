# Competitive Landscape

Accessed: 2026-07-13. Product descriptions and licenses are based on the sources
in [SOURCE_REGISTER.md](SOURCE_REGISTER.md); no third-party code has been copied.

| Product/research                              | Strength                                                                                      | Unsolved gap                                                                                                                                                                                  | Lesson                                                                                                                    | License/reuse                                                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| GitHub Forks list and Network graph           | Native identity, fork metadata, branch-history timeline, and familiar navigation              | Network graph shows at most 100 recently pushed branches and does not rank original development, deduplicate patches, cluster directions, or explain evidence                                 | Preserve GitHub links and lineage, but pair the graph with a filterable evidence table                                    | GitHub service and terms; interface behavior is reference material, not reusable code                          |
| Active Forks (`techgaun/active-forks`)        | Simple discovery and activity-oriented sorting                                                | Metadata-centric; no local commit graph, patch equivalence, confidence, composition, or multi-dimensional scoring                                                                             | A fast census is valuable before deep analysis                                                                            | `Apache-2.0 OR EUPL-1.2`; either license would require deliberate compliance and attribution before code reuse |
| Useful Forks                                  | Recursively searches sub-forks and filters forks with no main-branch commits after creation   | Main-branch/activity heuristic can miss release branches, rebases, equivalent patches, and maintained but low-frequency work                                                                  | Make shortlisting understandable and never equate one activity signal with usefulness                                     | MIT; reusable with notice, but this project reimplements concepts independently                                |
| Forkscout                                     | Fork discovery, feature-oriented reports, ranking, caching, and PR-oriented workflow          | Its public description emphasizes feature/value assessment and automated PRs; this MVP needs reproducible Git evidence, separate score dimensions, safe no-execution analysis, and no live AI | Feature-family presentation is valuable only when every claim resolves to commits, patches, and files                     | MIT; no code reused                                                                                            |
| GitHub Compare                                | Convenient ahead/behind and commit/file comparison for a selected pair                        | Pairwise and bounded; not a network census, patch-equivalence system, ranking engine, or cluster view                                                                                         | Link users back to the canonical compare page while computing complete local structural evidence                          | GitHub service and terms                                                                                       |
| Git `patch-id` / `cherry`                     | Mature deterministic identification of likely duplicate patches across rewritten commit IDs   | Does not establish semantic equivalence; squashes and similar independent implementations need separate methods                                                                               | Make equality levels explicit: same commit, same stable patch, normalized-diff similarity, shared area, semantic relation | Git is GPL-2.0; invoking the installed CLI does not copy its implementation into this repository               |
| Software Heritage, "Forking Without Clicking" | Shows that shared commits reveal fork/provenance relationships that forge-declared links miss | Global cross-forge reconstruction is beyond a GitHub public-fork MVP and can be computationally large                                                                                         | Keep identity and commit-graph layers separate so cross-forge genealogy remains possible later                            | Research paper is evidence; dataset/software terms require separate review before reuse                        |
| ForkVis, "Use the Forks, Look!"               | Researches visual search/tagging of related forks and fork-ecosystem exploration              | A visualization alone does not supply operational scoring, resumable analysis, exports, or patch provenance                                                                                   | Provide lineage and cluster views plus an accessible synchronized table                                                   | Research artifact; inspect its repository license before any implementation reuse                              |

## Product differentiation

Fork Intelligence combines four things that the reviewed tools generally split:

1. broad, progressive public-network discovery;
2. local commit-graph and stable-patch evidence;
3. separate, versioned, reproducible rankings and deterministic clusters;
4. claim-to-evidence navigation, comparisons, and provenance-rich exports.

The product does not promise a universal "best fork." It explains which fork is
strong under a named intent, how much data was available, and which artifacts
support the result. Popularity, activity, maintenance, originality, divergence,
compatibility, and adoption remain separate dimensions.

## Reuse policy

Competitive sources inform requirements and failure modes. Before any future
code, visual asset, dataset, taxonomy, or text is reused, record its exact source
revision, license, attribution, compatibility, and copied scope. Default to an
independent implementation based on public behavior and primary Git/GitHub
interfaces.
