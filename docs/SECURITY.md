# Security

The analyzed repository is hostile input. The service may inspect provider
metadata, Git objects, and bounded file content; it must never execute repository
code, scripts, hooks, package managers, build systems, tests, binaries, filters,
submodules, or network instructions.

## Required controls

### Input and network

- Accept only `owner/repository` and standard HTTPS `github.com/owner/repo` URLs.
- Normalize before access; reject userinfo, ports, alternate schemes/hosts,
  fragments, ambiguous paths, IP literals, and redirects leaving the allowlist.
- Construct API and clone URLs from validated owner/name rather than accepting
  arbitrary user-provided URLs. Public repositories only.

### Git subprocess

- Invoke a fixed Git executable with argument arrays, never a shell string.
- Use bare service-owned stores and exact encoded refs keyed by repository ID.
- Supply a minimal environment, controlled HOME, `GIT_CONFIG_NOSYSTEM=1`, an
  empty hooks path, disabled prompts, and restricted protocols.
- Never set `safe.directory=*`; quarantine unexpected ownership.
- Apply wall-clock, output, disk, blob, object, branch, fork, and concurrency
  limits. Cancellation must terminate the process group safely.
- Never include credentials in a remote URL or log.

### Content and browser

- Treat commit messages, paths, READMEs, issues, releases, and diffs as text.
- Escape structured fields and sanitize the narrow supported Markdown subset;
  never render repository HTML directly.
- Use a restrictive Content Security Policy and safe outbound links.
- Quote CSV and neutralize cells beginning with spreadsheet formula characters.
- No live AI is present; future AI requires a new ADR/threat review.

### Secrets and data

- Anonymous REST is the default. Optional GitHub tokens are server-side,
  read-only, least-privilege secrets and never appear in browser storage, query
  strings, analysis rows, events, logs, error detail, or exports.
- Do not read local `.env` files during analysis. Document names in
  `.env.example`; inject production secrets through the platform secret store.
- Retain only evidence needed for the disclosed analysis and enforce run/export/
  Git-cache retention. Self-hosted defaults are 30 days for analyses and 7 days
  for exports. Deletion is an authenticated operator action and is audited; no
  anonymous deletion endpoint is exposed.

## API controls

Use request/body limits, strict schemas, CORS allowlists, secure headers, opaque
IDs, idempotency, and per-IP/run admission/concurrency limits. Cancellation and
resume are idempotent. Do not leak whether a non-public repository exists.
Future saved/private analyses require authentication, authorization, and tenant
isolation before enablement.

## Dependency and build hygiene

Lock production dependencies, review changes, generate SBOMs where supported,
and scan source, dependencies, images, and secrets in CI. Do not install
dependencies declared by analyzed repositories. Base images and Git runtimes need
regular security updates and supported-version policy.

## Security validation checklist

- hostile URL/parser and redirect corpus;
- branch/ref argument-injection and traversal corpus;
- canary Git hooks, filters, binaries, and submodule URLs never execute/fetch;
- resource-limit fixtures terminate cleanly;
- logs/events/exports contain no seeded secret;
- XSS/Markdown and CSV-formula corpus;
- duplicate queue delivery and Redis restart preserve integrity;
- dependency, image, and secret scans reviewed;
- threat model and Git/GitHub assumptions rechecked before release.

## Reporting

Do not include secrets or hostile content in an issue. Record the affected
version, run/request IDs, sanitized reproduction, impact, and containment. Rotate
any potentially exposed credential, quarantine affected Git stores/exports, and
preserve audit evidence. Publish a security contact before public deployment.

See [THREAT_MODEL.md](architecture/THREAT_MODEL.md) for threats and residual risk.
