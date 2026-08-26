# Domain Docs

How the engineering skills should consume this repo's domain documentation
when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root. It does not exist yet — proceed silently.
- **`docs/architecture/adr/`** — the ADRs. Note this repo does **not** use the
  conventional `docs/adr/` path. Six ADRs exist, 0001 through 0006, covering
  the stack, GitHub API strategy, the safe bare Git store, deterministic
  methods, the no-live-AI decision, and SSE progress.
- **`docs/DECISIONS.md`** — a running one-line decision log (`D001`…) that is
  broader and terser than the ADRs. Read it alongside them; a decision may be
  recorded there and nowhere else.

If any of these don't exist, proceed silently. Don't flag their absence or
suggest creating them upfront. `/domain-modeling` creates them lazily when
terms or decisions actually get resolved.

## File structure

Single-context repo. Despite the pnpm workspaces (`apps/web`,
`services/platform`, `packages/contracts`), documentation is centralized under
`docs/` and every ADR is system-wide. There is no `CONTEXT-MAP.md` and no
per-workspace `adr/` directory.

```
/
├── CONTEXT.md                  ← not yet created
├── docs/
│   ├── DECISIONS.md
│   └── architecture/adr/
│       ├── 0001-system-stack.md
│       └── …
├── apps/web/
├── services/platform/
└── packages/contracts/
```

## Use the glossary's vocabulary

When your output names a domain concept — an issue title, a refactor proposal,
a hypothesis, a test name — use the term as defined in `CONTEXT.md`. Don't
drift to synonyms the glossary avoids.

If the concept isn't in the glossary yet, that's a signal: either you're
inventing language the project doesn't use, or there's a real gap worth noting
for `/domain-modeling`.

## Flag ADR conflicts

If your output contradicts an existing ADR or a `docs/DECISIONS.md` entry,
surface it explicitly rather than silently overriding:

> _Contradicts ADR-0005 (no live AI) — but worth reopening because…_
