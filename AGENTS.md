# Fork Intelligence Repository Guidance

## Purpose and layout

- `apps/web`: Next.js product UI; never call GitHub or Git directly.
- `services/platform`: FastAPI, worker, domain logic, and external adapters.
- `packages/contracts`: generated OpenAPI and TypeScript contracts.
- `fixtures`: deterministic hostile-input and Git-history fixtures.
- `docs`: architecture, methodology, research, security, and status.

## Commands

- Setup: `pnpm install && uv sync --directory services/platform --all-groups`
- Develop: `pnpm dev`
- Test: `pnpm test`
- Lint: `pnpm lint`
- Type check: `pnpm typecheck`
- Build: `pnpm build`
- Migrate: `pnpm db:migrate`

## Boundaries and security

- Analyzed repository code is untrusted and must never be executed.
- Shell interpolation with untrusted input is prohibited.
- Git subprocesses must use validated argument arrays, sterile configuration,
  timeouts, output limits, and exact allowlisted HTTPS GitHub remotes.
- Never check out analyzed repositories, run hooks, package managers, builds,
  tests, binaries, submodules, or repository-supplied commands.
- AI-generated claims require linked evidence; live AI is disabled in the MVP.
- Keep API handlers, long-running jobs, domain logic, and adapters separated.
- Shared contracts and core entities must not be changed casually by delegated
  agents; coordinate those edits through the lead integrator.
- Add tests with every behavior change. Generated contract files are committed
  because the repository validates drift.
- Keep secrets out of source and logs; use `.env.example` for documentation.

## Delegation and ownership

- Assign non-overlapping directory ownership before parallel edits.
- Do not edit root manifests, migration heads, contracts, or core entities from
  multiple workstreams simultaneously.
- Every handoff reports files, interfaces, tests, assumptions, limitations, and
  unmet acceptance criteria.

## Definition of done

A change is done when focused tests, lint, types, and relevant browser checks
pass; evidence and security boundaries remain intact; docs/status are current;
and the final diff contains no unrelated or generated runtime artifacts.

## Prohibited shortcuts

Do not ship mocked analysis as real, collapse all rankings into one score,
present patch similarity as semantic equivalence, hide sampling, bypass the
worker for long tasks, or claim validation that was not performed.
