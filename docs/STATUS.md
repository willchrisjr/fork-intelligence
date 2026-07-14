# Status

- Absolute project path: `/Users/wma/Codex/Developer/personal/fork-intelligence`
- Git root: `/Users/wma/Codex/Developer/personal/fork-intelligence`
- Branch: `main`
- Project state: new greenfield implementation in its dedicated repository
- Current milestone: M7 production-MVP validation complete

## Environment

- macOS on Apple Silicon
- Git 2.54.0
- Node.js 22.23.1, npm 10.9.8, pnpm 11.7.0
- Python 3.14.6, uv 0.11.21
- SQLite 3.54.0
- GitHub CLI authenticated and API reachable
- Colima 0.10.3, Docker CLI 29.6.1/server 29.5.2, Docker Compose 5.3.1
- PostgreSQL 17, Redis 7.4, API, worker, migration, and web containers were
  validated through the application Compose profile; the Colima daemon may be
  stopped between active development sessions

## Completed

- Dedicated project boundary and Git repository confirmed.
- Product specification, architecture, infrastructure choice, and design
  direction approved.
- Repository baseline and root development contracts completed.
- Non-privileged Docker runtime installed after Docker Desktop required an
  interactive administrator password; PostgreSQL and Redis health checks pass.
- Primary-source research, product/architecture documentation, ADRs, and the
  threat model are complete.
- pnpm and uv dependency graphs are locked; the approved native pnpm build
  scripts completed successfully.
- FastAPI, Dramatiq, PostgreSQL models/migration, Redis dispatch, durable
  checkpoints/events, GitHub REST traversal, safe Git intelligence, scoring,
  classification, clustering, comparison, exports, and recovery endpoints are
  implemented.
- Next.js submission, analysis workspace, fork detail, evidence inspector,
  comparison, evolution, directions, methodology, responsive states, and
  same-origin API proxy are implemented.
- A persisted, system-aware light/dark theme is available on every primary
  product surface, including theme-aware lineage and Cytoscape graph colors.
- GitHub development governance is repository-local and reviewable: contribution
  guidance, pull request/issue/security templates, code ownership, pinned-action
  CI, and weekly grouped dependency updates are configured.
- GitHub repository settings permit squash merges only, delete merged branches,
  require full commit SHAs for third-party Actions, and enable Dependabot
  vulnerability alerts and security updates.
- Independent security review completed with no P0 finding. Confirmed P1 issues
  were corrected: bounded Git I/O/deadlines, process-group termination,
  quarantined oversized stores, slash-safe refs, encoded GitHub paths, terminal
  SSE replay, safe queued-job redispatch, quota-paused partial state, admission
  limits, and immutable sealed exports.
- A final containerized `octocat/Hello-World` run completed with three forks
  discovered, two forks structurally analyzed, ordered event replay, evidence,
  scoring, one deterministic cluster, comparison, and exports.

## In progress

- None for the MVP handoff. The Compose stack is intentionally left running for
  local exploration.

## Blockers

- None. Live AI enrichment is intentionally disabled.

## Validation performed

- Project boundary, Git state, installed runtimes, GitHub connectivity, and
  container runtime verified.
- The complete Compose application profile builds and starts cleanly; migration,
  API readiness, worker, web, PostgreSQL, and Redis are healthy.
- pnpm lockfile passed local supply-chain policy verification; `sharp` and
  `unrs-resolver` were explicitly approved and built.
- Documentation internal-link/source-register checks passed; Markdown was
  formatted with Prettier.
- Ruff format/lint, strict mypy, 104 platform tests, 2 isolated PostgreSQL/Redis
  integration tests, 10 frontend unit tests, TypeScript, ESLint, Prettier,
  OpenAPI generation, contract types, and Next production build passed.
- Playwright passed 21 behavioral scenarios at desktop, mobile portrait, and
  mobile landscape; three reference captures also passed.
- Dark-mode persistence, workspace switching, and the production rendering were
  checked in Chromium; the latest dark landing render was compared directly to
  the accepted landing concept.
- Native-resolution concept/capture comparisons and a live Playwright CLI review
  covered landing, completed real analysis, comparison, evolution, responsive
  navigation, accessibility tree, headers, console, and evidence links.
- Migration upgrade, downgrade-to-base, upgrade, and isolated test-database
  upgrade were exercised.
- Real SSE replay returned the terminal event; deterministic JSON export returned
  a stable ETag; the final comparison returned exactly upstream plus two forks.

## Failed validation

- GitHub-hosted Actions returned `startup_failure` before creating any job for
  both the full schema-valid CI workflow and a temporary one-line smoke
  workflow. Repository Actions are enabled, but the authenticated CLI cannot
  inspect account billing/budget state without an additional credential scope.
- GitHub rejected secret scanning for this private repository under the current
  plan. Private-repository rulesets are also unavailable without GitHub Pro,
  Team, or Enterprise, so the documented pull-request policy is not yet
  server-enforced.
- The in-app Browser runtime failed during repeated initialization attempts with
  `Cannot redefine property: process`; the documented Playwright CLI/test
  fallback passed outside the macOS sandbox.
- A sandboxed Chromium run failed because macOS denied Mach-port registration;
  the approved unsandboxed browser run passed all 19 scenarios.
- Docker Desktop required an interactive administrator helper installation;
  approved Colima/Docker Compose provided the equivalent validated runtime.

## Next actions

1. Increase evidence coverage with authenticated GitHub acceleration, the
   three-branch planner, and bounded deep blob hydration.
2. Automate scheduled retention, durable-job reconciliation, observability, and
   backup/restore drills.
3. Improve saved/incremental investigations and upstream-absorption tracking.
4. Add authentication, tenant isolation, GitHub App/private-repository support,
   and stronger edge controls only before public or multi-tenant deployment.

Detailed sequencing and exit criteria are maintained in `docs/ROADMAP.md`.

## Active delegated workstreams

- Documentation and primary-source research: complete.
- Platform implementation: complete and lead-reviewed.
- Frontend implementation: complete and lead-reviewed.
- Synthetic fixtures and platform tests: complete.
- E2E browser workstream: complete.
- Independent security review: complete; confirmed findings integrated and
  revalidated.

## Recent decisions

- PostgreSQL is authoritative; Redis is a broker only.
- Core analysis is deterministic and works without an LLM key.
- REST is the anonymous GitHub baseline; GraphQL is an authenticated accelerator.
- Deep Git analysis is bounded and sampling is always disclosed.
- Theme selection is local browser state; it changes presentation only and does
  not alter analysis data or shared API contracts.
- `main` development is pull-request-first with green CI and squash merge. The
  private repository's current GitHub Free plan does not support server-enforced
  rulesets; upgrading to GitHub Pro would allow the documented policy to become
  mandatory branch protection.
- Public submission is admission-controlled; repeated analyses for one
  repository serialize, queue depth and disk watermarks are enforced, and Redis
  per-client throttling is a defense-in-depth layer.
- Exports are sealed, deterministic database artifacts; partial terminal
  checkpoints can export with their limitations intact.
