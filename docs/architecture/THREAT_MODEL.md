# Threat Model

## Assets and trust boundaries

Assets include GitHub credentials, service availability, PostgreSQL analysis
records, Git object storage, evidence integrity, exports, and user trust in
rankings. Trust boundaries exist at browser/API, API/GitHub, worker/GitHub,
worker/Git subprocess, worker/Git object store, queue/database, and export/browser.

Analyzed repositories, repository metadata, commit messages, paths, blobs,
issues, releases, webhook payloads, and all submitted locators are hostile input.

## Threats and controls

| Threat                                  | Primary controls                                                                                                                                    | Verification                                            |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Shell or argument injection             | Parse only GitHub locators; construct canonical HTTPS remotes; fixed executable and argv arrays; `--`/exact refspec boundaries; strict ref encoding | parser/property tests and hostile branch/name fixtures  |
| Repository code execution               | bare stores, no checkout, hooks path empty, no submodules/filters/package managers/builds/tests/imports, restricted protocols                       | canary hook/binary fixtures must never run              |
| SSRF / arbitrary fetch                  | allowlist `github.com` and GitHub API endpoints after normalization; reject userinfo, ports, alternate schemes, IPs, redirects off allowlist        | URL corpus and redirect tests                           |
| Malicious Git config/ownership          | minimal environment, `GIT_CONFIG_NOSYSTEM`, controlled HOME, service-owned stores, no global `safe.directory=*`                                     | subprocess environment tests and ownership failure test |
| Resource exhaustion / Git bombs         | fork/branch/blob/object/time/output/storage/concurrency caps; partial clone; shortlist; per-network locks; cancellation                             | limit fixtures and timeout tests                        |
| Token disclosure                        | server-side secrets only; scoped read access; redacted structured logs; never include tokens in URLs, DB analysis rows, events, or exports          | secret scanners and log assertions                      |
| Stored/reflected XSS                    | render structured fields as text, sanitize allowed Markdown, prohibit raw repository HTML, safe outbound-link attributes                            | browser security tests and sanitizer tests              |
| Prompt injection                        | no live AI in MVP; repository text remains data; future provider requires structured bounded evidence and validated evidence IDs                    | architecture gate before adding any provider            |
| Evidence tampering or stale conclusions | immutable snapshots, sealed head SHAs, content digests, algorithm versions, provenance, ordered events, explicit staleness                          | reproducibility and migration tests                     |
| Cross-run data leak                     | run-scoped foreign keys/queries, opaque IDs, no private repository support, authorization boundary before saved/private work                        | integration tests                                       |
| Queue loss / duplicate work             | PostgreSQL checkpoints/events are durable; idempotency keys and work-item uniqueness; Redis is disposable                                           | Redis restart and duplicate-delivery tests              |
| Malicious export / formula injection    | quote CSV, prefix dangerous spreadsheet-leading formulas, escape Markdown/JSON correctly, bounded filenames/content                                 | export corpus tests                                     |
| Dependency/supply-chain compromise      | lock dependencies, review updates, minimal production set, CI scanning, no install from analyzed repos                                              | lockfile and scanner checks                             |

## Abuse cases

- Repeated anonymous submissions can consume the shared GitHub IP quota. Apply
  per-IP/run concurrency limits and reuse idempotent cached public analyses.
- Huge public networks can fill disk. Enforce admission budgets, progressive
  shortlisting, retention, and low-watermark rejection before fetch.
- A repository can contain misleading claims or crafted names. Never treat text
  as instructions; distinguish provider facts, calculations, and heuristics.
- An attacker can cause stale-name collisions through transfers. Key identity
  and refs by stable repository ID and preserve locator history.

## Residual risks

Git parser vulnerabilities, GitHub behavior changes, imperfect generated/vendor
classification, rename heuristics, and undisclosed secondary limits remain.
Run workers with least privilege in an isolated container/process account,
maintain supported Git versions, expose uncertainty, and support rapid cache
purge. Private repositories, arbitrary forges, webhook ingestion, and live AI
are outside the MVP threat surface and require a new review before enablement.
