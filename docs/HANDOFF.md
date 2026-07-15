# Fork Intelligence Session Handoff

Updated: 2026-07-15

This document is the durable starting point for the next implementation session.
Read `AGENTS.md`, `CONTRIBUTING.md`, this file, and `docs/STATUS.md` before
editing. Prefer current repository and GitHub state over any stale value recorded
here.

## Copy into the next Codex session

> Continue Fork Intelligence from
> `/Users/wma/Codex/Developer/personal/fork-intelligence`. Read `AGENTS.md`,
> `CONTRIBUTING.md`, `docs/HANDOFF.md`, `docs/STATUS.md`, and `docs/ROADMAP.md`.
> Inspect current Git and GitHub state before editing. First verify whether GitHub
> billing issue #2 is resolved and restore required hosted CI. Then resolve the
> two open moderate Dependabot alerts in focused pull requests. After governance
> is green, begin Priority 1 analysis coverage in this order: authenticated
> GraphQL acceleration with REST fallback, deterministic three-branch planning,
> bounded explicit blob hydration, and real-network coverage benchmarks. Follow
> the protected-`main` pull-request workflow and never execute analyzed code.

## Project identity and current state

- Local root: `/Users/wma/Codex/Developer/personal/fork-intelligence`
- GitHub: <https://github.com/willchrisjr/fork-intelligence>
- Visibility: public
- Default branch: `main`
- Baseline before this handoff PR: `43fb0d5`
- Product state: production-quality single-tenant/self-hosted MVP implemented
  and validated end to end
- Open pull requests at handoff start: none
- Open operational issue:
  [#2 Unblock GitHub Actions startup failures](https://github.com/willchrisjr/fork-intelligence/issues/2)
- `Protect main` ruleset ID: `18920914`

The ruleset is active with no bypass actors. It requires pull requests, resolved
review threads, linear history, and squash-only merges. It blocks deletion and
force pushes. Required CI is deliberately not yet part of the ruleset because
GitHub cannot assign a runner while the account is billing-locked.

Repository settings also enforce full-SHA GitHub Action references, enable
Dependabot security updates, delete merged branches, and enable secret scanning
plus push protection.

## Immediate user action: unlock GitHub billing

The definitive annotation on
[Actions run 29320561933](https://github.com/willchrisjr/fork-intelligence/actions/runs/29320561933)
is:

> The job was not started because your account is locked due to a billing issue.

This is an account-level GitHub setting and must be handled by the account owner.
Do not expand CLI credential scopes or attempt to handle payment data in Codex.

1. Sign in as `willchrisjr` and open <https://github.com/settings/billing>.
2. Open **Billing & Licensing**, then **Payment information**.
3. Check payment history and clear any past-due balance. Update or reauthorize
   the card or PayPal account if the prior payment or authorization failed.
4. Open **Budgets and alerts**. Inspect account-level and repository-level
   GitHub Actions budgets. Increase or remove any exhausted zero-dollar budget
   that has **Stop usage when budget limit is reached** enabled. Avoid overlapping
   account and repository hard-stop budgets.
5. Enable included-usage alerts and budget threshold alerts so a future lock is
   visible before CI stops.
6. Wait for GitHub to process the payment or authorization. GitHub documents
   automatic unlocking after successful processing and notes that processing may
   take up to 24 hours.
7. If the account remains locked after successful payment processing, contact
   GitHub Billing Support and include the run URL and exact annotation above.
   Never put payment details, tokens, or private billing screenshots in a public
   issue.

Public repositories using standard GitHub-hosted runners do not consume paid
Actions minutes, but an existing account billing lock still prevents runner
assignment until GitHub clears it.

Official references:

- <https://docs.github.com/en/billing/how-tos/troubleshooting/locked-account>
- <https://docs.github.com/en/billing/managing-your-github-billing-settings/adding-or-editing-a-payment-method>
- <https://docs.github.com/en/billing/how-tos/set-up-budgets>
- <https://docs.github.com/en/billing/concepts/product-billing/github-actions>

## P0 — Restore enforceable CI governance

Do this immediately after the billing state is corrected.

1. Confirm local `main` is clean and current:

   ```bash
   git switch main
   git pull --ff-only
   git status --short --branch
   ```

2. Dispatch CI and watch the actual job:

   ```bash
   gh workflow run CI --repo willchrisjr/fork-intelligence --ref main
   gh run list --repo willchrisjr/fork-intelligence --workflow CI --limit 5
   gh run watch RUN_ID --repo willchrisjr/fork-intelligence --exit-status
   ```

3. If the job fails before any steps, inspect the check-run annotation rather
   than guessing from an empty log. If steps execute, diagnose the first real
   failure and fix it through a focused branch and pull request.
4. After `CI / checks` passes on `main` and on a pull request, edit the active
   `Protect main` ruleset and add `checks` as a required status check. Require
   the branch to be current with `main` before merging.
5. Verify the ruleset through the API and confirm there are still no bypass
   actors.
6. Close issue #2 with the billing cause, remediation date, successful run URL,
   and final ruleset configuration.
7. Remove the temporary billing-lock exception from `CONTRIBUTING.md`,
   `docs/STATUS.md`, and this handoff.

Acceptance criteria:

- Manual, push, and pull-request CI jobs obtain a runner and pass.
- `checks` is required on `main` and cannot be bypassed routinely.
- A test pull request cannot merge while `checks` is pending or failing.
- Issue #2 records the verified resolution and is closed.

## P0 — Resolve current dependency alerts

Do not silently dismiss these alerts or add a broad override without proving why
it is safe.

### Pytest alert

- Alert: <https://github.com/willchrisjr/fork-intelligence/security/dependabot/2>
- Current: `pytest 8.4.2`
- Vulnerable range: `<9.0.3`
- First patched version: `9.0.3`
- Constraint: `pytest>=8.4,<9` in `services/platform/pyproject.toml`
- Consequence: remediation requires an intentional pytest major-version update,
  not merely regenerating `uv.lock`.

Recommended pull request:

1. Create `agent/security-pytest-9`.
2. Review pytest 9 migration notes and update the dev constraint to a bounded
   compatible range beginning at `9.0.3`.
3. Regenerate only the Python lockfile with uv.
4. Run Ruff, strict mypy, all platform tests, PostgreSQL/Redis integration tests,
   migrations, and the complete CI command.
5. Confirm the Dependabot alert closes after merge.

### PostCSS alert

- Alert: <https://github.com/willchrisjr/fork-intelligence/security/dependabot/1>
- Vulnerable instance: `postcss 8.4.31`
- Vulnerable range: `<8.5.10`
- First patched version: `8.5.10`
- Dependency path: `next 16.2.10 -> postcss 8.4.31`
- A separate safe `postcss 8.5.18` is already used by Tailwind/Vite tooling.

Recommended pull request:

1. Create `agent/security-postcss`.
2. Run `pnpm why postcss` and determine whether a reviewed Next.js patch update
   removes the vulnerable transitive version.
3. Prefer an upstream-compatible Next.js update. Use a pnpm override only if
   Next's declared compatibility and the application build/tests prove it safe;
   record the rationale if an override is necessary.
4. Regenerate only `pnpm-lock.yaml` and inspect the complete lockfile diff.
5. Run frontend unit tests, lint, type checks, production build, full CI, and
   Playwright because the vulnerable package is in the web build chain.
6. Confirm the Dependabot alert closes after merge.

Acceptance criteria:

- Both alerts close without dismissal.
- Lockfile changes are minimal and explained.
- Complete local and hosted validation passes.
- Major or security-sensitive dependency changes are not auto-merged.

## P1 — Increase deterministic analysis coverage

Start only after P0 governance and security work is green. Deliver these as
separate milestones and pull requests.

### 1. Authenticated GraphQL metadata accelerator

Primary files:

- `services/platform/src/fork_intelligence/adapters/github.py`
- `services/platform/src/fork_intelligence/config.py`
- `services/platform/src/fork_intelligence/services/pipeline.py`
- `tests/platform/test_github.py`
- `tests/platform/test_api_postgres_integration.py`
- `docs/architecture/adr/0002-github-api-strategy.md`

Required behavior:

- Keep anonymous REST as the correct baseline.
- Use a server-side scoped token only; never expose it to the browser or logs.
- Add GraphQL as an optional traversal/batching accelerator with explicit cost
  budgeting, cursor checkpoints, partial-error handling, timeouts, and schema
  fixtures.
- Deduplicate every repository by stable GitHub repository ID.
- Fall back to REST on GraphQL partial errors, budget exhaustion, timeout, or
  schema drift without losing durable progress.
- Persist request mode, quota/cost, coverage, and field-level provenance.

Acceptance criteria:

- Deterministic fixtures cover pagination, partial GraphQL errors, rate limits,
  nested/direct forks, deleted/inaccessible repositories, and REST fallback.
- Anonymous mode remains fully functional and honest about partial coverage.
- Authenticated mode materially increases accessible coverage in a real capped
  network test.

### 2. Deterministic three-branch planner

Primary files:

- `services/platform/src/fork_intelligence/services/pipeline.py`
- `services/platform/src/fork_intelligence/adapters/github.py`
- `services/platform/src/fork_intelligence/models.py`
- `services/platform/src/fork_intelligence/api/routes.py`
- `tests/platform/test_github.py`
- a new focused domain test/module if selection logic is extracted

Current limitation: `_structural` analyzes only each repository's default
branch even though `max_branches_per_fork` is already configured as three.

Required behavior:

- Enumerate branches safely and checkpoint API pagination.
- Select default first, then recently active and meaningfully ahead branches
  within the configured cap.
- Keep selection deterministic with a versioned rule and stable tie-breakers.
- Persist included and excluded branches plus selection reasons.
- Fetch only exact validated heads and keep all existing Git safety boundaries.
- Surface branch selection and coverage in API/UI evidence.

Acceptance criteria:

- Fixtures cover malicious refs, duplicate heads, moved branches, pagination,
  default-only repositories, and deterministic ties.
- The UI/API explains why each branch was included or excluded.
- Analysis caps remain enforceable and visible.

### 3. Bounded explicit blob hydration

Primary files:

- `services/platform/src/fork_intelligence/adapters/git.py`
- `services/platform/src/fork_intelligence/services/pipeline.py`
- `tests/platform/test_git_analysis.py`
- `fixtures/git/build_fixture.py`
- `docs/architecture/adr/0003-safe-bare-git-store.md`

Current limitation: `fetch_branch` performs a best-effort blob-limited fetch,
and `compare` reports patch fingerprints as missing when required blobs remain
unavailable. It does not yet explicitly plan and hydrate only the bounded blobs
needed for shortlisted commit evidence.

Required behavior:

- Keep authoritative ancestry full-depth and blob-filtered; never substitute a
  shallow clone.
- Identify only the blobs needed for the bounded unique-commit shortlist.
- Hydrate through validated fixed Git argument arrays and the allowlisted HTTPS
  GitHub origin.
- Enforce per-blob, aggregate-store, command-output, and deadline limits.
- Preserve an explicit `missing_blobs` result for oversized, absent, or failed
  hydration; do not fabricate patch evidence.
- Recompute patch IDs and file/dependency evidence only for successfully
  hydrated content.

Acceptance criteria:

- Synthetic fixtures cover absent and oversized blobs, binaries, renames,
  partial fetch failure, corrupt objects, and successful resume.
- Patch coverage improves on the capped real smoke without weakening resource
  limits or executing repository content.
- Evidence clearly separates available fingerprints from missing data.

### 4. Coverage and performance benchmark

Run capped authenticated and anonymous analyses against small, medium, and large
fork networks. Record:

- accessible versus expected repositories;
- REST requests and GraphQL cost;
- branches selected/excluded;
- deep repositories and commit/patch coverage;
- elapsed time by stage;
- Git-store and database growth;
- degraded, quota, retry, and partial-result behavior.

Update `docs/PERFORMANCE.md`, `docs/STATUS.md`, methodology disclosures, and
source/version information. Do not publish credentials, private data, or
unbounded raw repository content.

## P2 — Operations and recovery

After coverage work is stable:

1. Implement scheduled retention with dry-run output, audit counts, active-run
   protection, and safe handling of exports and unreferenced Git stores.
2. Add periodic reconciliation for authoritative queued/running PostgreSQL state
   after Redis or worker loss.
3. Add structured metrics and alerts for queue age, stage latency, GitHub quota,
   Git failure, disk watermarks, SSE lag, retries, and stalled analyses.
4. Automate PostgreSQL backup/restore drills and document recovery objectives.

Likely ownership boundaries:

- retention/reconciliation: platform services, worker, models/migrations;
- metrics: API/worker instrumentation and operations documentation;
- restore drills: `scripts`, Compose/infra, and `docs/OPERATIONS.md`.

Each behavior change requires fault-injection or integration tests. Do not make
Redis authoritative and do not delete active or referenced data.

## P3 — Investigator workflow

Only after P1/P2 foundations:

- immutable saved labels and incremental refresh;
- repository health alerts and upstream-absorption tracking;
- additional dependency ecosystems and stronger deterministic change families;
- comparison annotations and maintainer evidence queues.

Every interpretation must retain evidence, provenance, confidence, coverage,
algorithm version, and deterministic fallback behavior.

## Deferred until deployment scope changes

- Authentication, tenant authorization, GitHub App installations, private
  repository analysis, webhooks, and audit logs are required before public or
  multi-tenant service deployment.
- Live LLM enrichment requires a new ADR and prompt-injection review.
- Non-GitHub forges, advanced semantic equivalence, vulnerability scanning of
  analyzed repositories, automatic PRs, and automatic merges remain deferred.

## Environment and startup notes

Last observed tools:

- Node.js `22.23.1`
- pnpm `11.7.0`
- uv `0.11.21`
- Python `3.14.6` locally; project targets Python 3.13+
- Git `2.54.0`
- Docker CLI `29.6.1`
- standalone `docker-compose 5.3.1`
- Colima installed but stopped at handoff time

This machine currently exposes Compose through `docker-compose`, not
`docker compose`. Start infrastructure with:

```bash
colima start
pnpm infra:up
pnpm db:migrate
```

The default uv cache under `~/.cache/uv` may be blocked by the Codex filesystem
sandbox. For local verification in Codex, use a temporary cache:

```bash
UV_CACHE_DIR=/tmp/fork-intelligence-uv-cache pnpm check:ci
pnpm test:e2e
```

Use `pnpm stack:up` for the complete Compose profile. Do not remove persistent
volumes unless the user explicitly authorizes destructive cleanup.

Last complete validation snapshot:

- 104 platform tests passed; 2 environment-gated integration tests skipped in
  the non-integration invocation;
- 10 frontend unit tests passed;
- Ruff, ESLint, strict mypy, TypeScript, formatting, contracts, secret scan, and
  production build passed;
- 21 Playwright scenarios passed across desktop, mobile portrait, and mobile
  landscape;
- a real `octocat/Hello-World` containerized analysis completed end to end.

Treat these as historical evidence, not a substitute for rerunning checks after
changes.

## Delegation plan

Use at most two or three parallel workstreams after interfaces are defined:

1. GitHub adapter and fixtures owns only `adapters/github.py` and its focused
   tests/research.
2. Git/branch analysis owns `adapters/git.py`, any new deterministic branch
   selection module, Git fixtures, and focused tests.
3. A reviewer inspects security, API contracts, and test coverage without
   independently changing shared models or root manifests.

The lead agent owns architecture, `config.py`, shared models/schemas, pipeline
integration, generated contracts, migrations, root manifests, final validation,
and documentation. Do not allow parallel edits to shared contracts, migration
heads, core entities, or root lockfiles.

## Definition of done for the next cycle

- GitHub billing is unlocked and issue #2 is closed with evidence.
- Hosted `checks` passes and is required by the `Protect main` ruleset.
- Both current moderate dependency alerts are remediated and closed.
- GraphQL acceleration, branch planning, and bounded blob hydration each ship in
  focused reviewed pull requests with deterministic tests and documented
  evidence/provenance behavior.
- Anonymous REST remains correct; authenticated mode improves coverage.
- Complete local, integration, contract, browser, migration, security, and real
  capped smoke validation passes.
- `docs/STATUS.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, and this handoff match
  the final system.

## Non-negotiable safety boundaries

- Analyzed repository code is untrusted and must never be executed.
- Never interpolate untrusted input into a shell.
- Git subprocesses use validated argument arrays and sterile configuration.
- Never expose GitHub tokens, billing data, `.env`, or private repository data.
- Never claim semantic equivalence from stable patch IDs alone.
- Never hide sampling, missing blobs, API coverage, confidence, or provenance.
- Never push routine feature work directly to `main`, force-push shared history,
  or bypass the ruleset.
