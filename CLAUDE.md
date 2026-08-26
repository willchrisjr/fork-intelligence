# Fork Intelligence — Claude Code guidance

**Read `AGENTS.md` first.** It is the canonical repo guidance — layout, commands,
and the security boundaries — and applies to Claude exactly as it does to Codex.
Do not duplicate its content here; this file covers only what AGENTS.md omits.

## The invariant that must not erode

Analyzed repositories are hostile input. Inspect Git objects; never check out,
build, or execute analyzed repo code, hooks, or package managers. Any feature
request that amounts to "just run it to see if it works" violates the product's
core security claim — raise it rather than implementing it.

## Local environment facts

- Clone lives at `~/Codex/Developer/personal/fork-intelligence`. This is the only
  clone; do not make a second one (see below).
- `.env` does not exist yet — only `.env.example`. The Docker stack is not
  configured to run locally as of 2026-08-10.
- Docker runs via colima, which is often not started. Check before `compose up`.

## Do not make a second clone

`compose.yaml` pins `name: fork-intelligence`, so Compose project and named
volume identities (`postgres-data`, `redis-data`, `git-data`) are shared by any
copy of this tree. A second clone silently attaches to the same Postgres and
Redis instead of getting an isolated stack.

Use `git worktree` for isolation instead. Two caveats specific to this repo:

- The pinned Compose name collides across worktrees too. To run the stack in
  one, override it: `COMPOSE_PROJECT_NAME=fork-intelligence-<task> docker compose up`.
- pnpm workspaces do not share `node_modules`; each worktree costs its own
  install (~816M). Cheap for a review branch, wasteful for several at once.

## Shared with Codex

Codex works this repo directly and owns `AGENTS.md`. Never run Claude and Codex
against the same files at the same time. When delegating file edits to Codex,
give it a worktree per the global delegation policy in `~/.claude/CLAUDE.md`.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `willchrisjr/fork-intelligence`, via the `gh`
CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context. Note the non-standard ADR path — `docs/architecture/adr/`, not
`docs/adr/`. See `docs/agents/domain.md`.
