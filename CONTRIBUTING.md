# Contributing

Fork Intelligence uses short-lived branches, pull requests, required CI, and a
linear `main` history. These rules apply to human and agent-authored changes.

## Start work

1. Sync `main` and confirm the working tree is clean.
2. Create a focused branch: `feature/<slug>`, `fix/<slug>`, `docs/<slug>`, or
   `chore/<slug>`. Codex uses `agent/<slug>`.
3. Read `AGENTS.md` and any nested instructions before editing.
4. Keep one pull request focused on one coherent outcome.

Do not commit or push feature work directly to `main`. Do not force-push a
shared branch or bypass repository rules for routine work.

## Develop safely

- Preserve unrelated changes and inspect untrusted repositories as data only.
- Add tests with behavior changes.
- Update documentation, contracts, migrations, fixtures, and threat decisions
  when the behavior they describe changes.
- Generate OpenAPI/TypeScript contracts with `pnpm contracts`; do not hand-edit
  generated contract output.
- Never commit secrets, `.env`, credentials, runtime data, caches, or browser
  artifacts.

## Validate

Run the smallest relevant checks while iterating, then before requesting review:

```bash
pnpm check:ci
```

For frontend or end-to-end workflow changes, also run:

```bash
pnpm test:e2e
```

If a check cannot run locally, explain why and identify the residual risk in the
pull request. CI must still pass before merge.

## Commit and pull request

- Use logical commits with terse imperative subjects, such as
  `fix(platform): preserve terminal event replay`.
- Review `git status`, `git diff --check`, and the staged diff before committing.
- Push the branch and open a draft pull request early for non-trivial work.
- Complete the pull request template with scope, testing, security, contracts,
  documentation, and limitations.
- Resolve review conversations and keep the branch current with `main`.

Use squash merge after required checks pass, then delete the merged branch.
Administrator bypass is reserved for a documented emergency recovery and must be
followed by a corrective pull request.

GitHub currently cannot enforce the documented `main` policy for this private
repository on its plan. This is a platform limitation, not permission to bypass
the workflow: contributors and development agents must still follow it. If the
repository is upgraded to GitHub Pro, Team, or Enterprise, configure the rule as
mandatory immediately.

## Dependency updates

Dependabot proposes weekly grouped updates for pnpm, uv, GitHub Actions, and
container definitions. Review release notes and lockfile changes, run the normal
checks, and avoid automatic merging of major or security-sensitive updates.
