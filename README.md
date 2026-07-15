# Fork Intelligence

Fork Intelligence is a self-hosted repository evolution platform that finds the
GitHub forks containing meaningful original development and explains every
ranking, classification, and comparison with inspectable evidence.

## Current status

The production MVP is implemented and validated end to end. It accepts a public
GitHub repository, progressively discovers its accessible fork network,
analyzes a bounded shortlist with native Git, and exposes evidence-backed
rankings, fork details, comparisons, development directions, evolution views,
JSON/CSV/Markdown exports, and a persisted system-aware light/dark theme.

## Architecture

- Next.js and TypeScript web application
- FastAPI API and Python analysis worker
- PostgreSQL as the durable system of record
- Redis as the job broker
- One bare Git object store per analyzed fork network
- OpenAPI-generated web contracts

Analyzed repositories are hostile input. Fork Intelligence inspects Git objects
but never checks out or executes repository code, hooks, package managers,
builds, tests, or binaries.

## Prerequisites

- Docker Engine with Docker Compose (Docker Desktop or Colima on macOS)
- Node.js 22+
- pnpm 11+
- Python 3.13+
- uv
- Git 2.45+

## Setup

```bash
cp .env.example .env
pnpm install
uv sync --directory services/platform --all-groups
docker-compose up -d postgres redis
pnpm db:migrate
```

`GITHUB_TOKEN` is optional. Anonymous public-repository analysis works with a
lower API quota. Never commit `.env`.

The Compose credentials are development-only and both service ports bind to
localhost. Replace all credentials and use private service networking before a
non-local deployment.

## Development

```bash
pnpm dev
```

The web app runs at `http://localhost:3000` and the API at
`http://localhost:8000`.

To build and run the complete containerized stack, including the one-shot
database migration, API, worker, and web application:

```bash
pnpm stack:up
```

Use `pnpm stack:down` to stop it. Persistent PostgreSQL, Redis, and Git-store
volumes are retained unless an operator explicitly removes them.

## Verification

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
# Opt-in network check (consumes GitHub quota)
pnpm smoke:real
```

See [PLANS.md](PLANS.md), [docs/STATUS.md](docs/STATUS.md),
[docs/HANDOFF.md](docs/HANDOFF.md), [docs/ROADMAP.md](docs/ROADMAP.md), and
[docs/METHODOLOGY.md](docs/METHODOLOGY.md) for the current implementation scope,
validated behavior, session handoff, priorities, methodology, and limitations.

The most recent real-repository smoke analyzed `octocat/Hello-World` with a
three-fork census and two-fork structural shortlist. The full network was
intentionally sampled and the UI/API disclose that cap.

## Contributing

Development uses short-lived branches, pull requests, squash merges, and
automated dependency proposals. Required hosted CI is temporarily blocked by the
tracked GitHub account billing lock; complete local validation and a documented
exception are required until it is restored. Read
[CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) before changing the
repository. Do not push feature work directly to `main`.
