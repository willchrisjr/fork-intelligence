# Product Requirements

## Product promise

Fork Intelligence shows what happened to a project outside its main repository.
Given a public GitHub repository, it identifies forks with meaningful original
development, explains their directions and maintenance signals, and links every
important conclusion to commits, patches, paths, releases, or provider metadata.

The product does not declare one universal "best fork." It ranks forks under
separate, named intents and shows uncertainty, coverage, sampling, and method
versions.

## Users and jobs

| User                | Primary job                                                     |
| ------------------- | --------------------------------------------------------------- |
| Open-source user    | Find an active, maintained, or better-suited fork               |
| Maintainer          | Discover valuable work that never reached upstream              |
| Contributor         | Avoid duplicate work and compare implementations                |
| Technical evaluator | Compare variants for adoption, migration, or diligence          |
| Researcher          | Study fragmentation, specialization, succession, and innovation |

## MVP outcomes

A user can:

1. submit `owner/repository` or a standard public GitHub URL;
2. resolve the requested repository, parent, source, and accessible network;
3. see a progressive fork census before deep analysis completes;
4. distinguish synchronized, contribution, experimental, specialized, patch,
   continuation, independent-direction, and unknown forks with confidence;
5. rank forks separately by popularity, activity, sustained activity,
   maintenance, originality, divergence, adoption, compatibility, successor
   likelihood, and unmerged-innovation relevance;
6. inspect score inputs, missing data, depth, method version, and evidence;
7. inspect default/priority-branch Git relationships, unique commits, stable
   patches, composition, releases, dependencies, clusters, and limitations;
8. compare upstream with at least two forks;
9. navigate lineage and deterministic development-direction clusters through a
   graph or equivalent accessible table;
10. export JSON, CSV fork rows, and a Markdown report with provenance.

## Functional requirements

### Submission and resolution

- Allow only GitHub public repository identifiers and canonical HTTPS URLs.
- Reject malformed, ambiguous, alternate-host, userinfo, port, query/fragment,
  and option-injection input.
- Resolve by stable GitHub identity and preserve requested/canonical locators.
- Expose archived, disabled, unavailable, transferred, and fork states.

### Progressive analysis

- Stages: validation, resolution, census, shortlist, fetch, structural, deep,
  scoring/classification, clustering, finalization.
- Show ordered progress, partial results, discovered/shortlisted/deep counts,
  quota state, warnings, sampling, errors, retry, resume, and cancel.
- A single fork failure must not discard valid network results.

### Evidence and interpretation

- Label every field/conclusion as provider-sourced, locally calculated, or
  heuristic.
- Every classification, score explanation, cluster, and comparison conclusion
  links to evidence IDs.
- Stable patch equality is deterministic evidence; normalized similarity and
  semantic relation use cautious, distinct labels.
- No live AI is used in the MVP.

### Rankings

- Raw metrics remain independently queryable from normalized scores.
- Every score includes value, formula/weights, version, confidence, coverage,
  available/missing inputs, depth, and calculation time.
- Popularity is never used as a proxy for technical merit; divergence is not
  presented as inherently good.

### Exports

- JSON preserves the full analysis schema and provenance.
- CSV contains one fork per row with explicit score/confidence/coverage columns
  and formula-injection protection.
- Markdown provides a readable evidence-linked summary.
- All exports include analysis/configuration/method versions, source retrieval
  times, caps, sampling, and limitations.

## Experience requirements

Follow the approved `docs/DESIGN_CONTRACT.md`. The landing page prioritizes
repository input and mode choice. The analysis workspace prioritizes an evidence
table/viewport with synchronized inspector and visible operational state. The
comparison preserves upstream plus two forks. No graph-only conclusion is
allowed: keyboard and screen-reader users receive the same information in a
table. Loading, empty, partial, stale, sampled, rate-limited, error, cancelled,
and resumed states are first-class.

## Non-functional requirements

- Never execute analyzed repository code; use bare stores and safe Git argv.
- Anonymous REST is functional; authenticated GraphQL is optional acceleration.
- Jobs are idempotent, checkpointed, retryable, resumable, and observable.
- Deterministic methods reproduce the same output for identical sealed inputs
  and method versions.
- A clean environment can start web, API, worker, PostgreSQL, and Redis using the
  documented workflow.
- Normal CI does not need a GitHub token or external availability.

## MVP exclusions

Private repositories, GitLab/Bitbucket, arbitrary forges, automated PR/merge/
cherry-pick actions, analyzed-code execution, full vulnerability/SCA scanning,
continuous monitoring, organization portfolios, billing, enterprise tenancy,
mobile apps, and live AI are not MVP features.

## Acceptance criteria

The MVP is acceptable when the complete primary flow works against a real public
repository; synthetic Git fixtures prove ahead/behind/divergence and covered
rebase/cherry-pick/squash cases; score and cluster outputs are reproducible and
evidence-linked; partial/rate-limited/retry/resume states are visible; all three
exports work; security tests show repository content is never executed; and unit,
integration, contract, end-to-end, lint, type, build, browser, and opt-in real
repository checks are reported without overstating unrun validation.
