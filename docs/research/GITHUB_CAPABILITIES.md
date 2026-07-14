# GitHub Capability Research

Status: architecture baseline
Accessed: 2026-07-13
Primary sources: GitHub documentation listed in [SOURCE_REGISTER.md](SOURCE_REGISTER.md)

## Decisions

- Use GitHub REST as the required public-data path. The fork-list endpoint works
  without authentication for public repositories.
- Send `Accept: application/vnd.github+json` and pin the configurable
  `X-GitHub-Api-Version` header to the currently verified `2026-03-10` version.
- Use authenticated GraphQL only as an accelerator for field-selective metadata
  batching. Analysis must remain correct when GraphQL is unavailable.
- Treat repository numeric/node IDs as identity and owner/name as mutable
  locators. Preserve requested, resolved, parent, and source relationships.
- Never claim a complete census. Report the accessible, observed network and the
  pages, limits, failures, and exclusions that produced it.

## REST capabilities

### Repository and network resolution

`GET /repos/{owner}/{repo}` provides the repository record and, for a fork,
`parent` and `source` repository objects. Resolution therefore follows the API
relationship rather than guessing from Git remotes or names. Persist:

- requested locator and resolution time;
- stable GitHub repository ID and node ID;
- immediate parent and network source when present;
- default branch, `archived`, `disabled`, visibility, timestamps, size,
  language, license, topics, and counts;
- redirect or unavailability outcome.

GitHub defines a repository network as the upstream repository plus direct and
nested forks. The fork-list endpoint documents the forks of the repository being
queried but does not provide a completeness guarantee for inaccessible, deleted,
or detached repositories. The crawler must follow pagination and preserve the
reported `parent`/`source` relationships rather than flattening provenance.

Repository transfers and renames can change the canonical owner/name. Follow
safe GitHub redirects, re-resolve the canonical record, and retain the original
locator. A `404` is ambiguous between deletion, privacy, and lack of access; a
disabled or archived record is not equivalent to a missing record. Archived
repositories are valid analysis inputs but are labeled read-only and historical.

### Forks, branches, releases, and comparisons

- `GET /repos/{owner}/{repo}/forks` accepts `newest`, `oldest`, `stargazers`, or
  `watchers` sorting and up to 100 records per page.
- Branch, release, contributor, workflow, issue, and pull-request endpoints can
  enrich the census, subject to permissions, pagination, and cost.
- `GET /repos/{owner}/{repo}/compare/{basehead}` is useful for preview and
  corroboration, but the GitHub response has pagination and file-list bounds.
  The local Git engine remains authoritative for full reachability, merge bases,
  ahead/behind, and patch calculations.
- Default-branch analysis is only stage one. Recently active, release-linked,
  ahead-of-upstream, and open-PR branches are progressively selected.

Counts in repository responses are indicators, not proof of quality. In
particular, watchers/stargazers aliases and timestamps must retain their exact
source field; `updated_at` and `pushed_at` are not interchangeable with a latest
meaningful commit.

### Pagination and conditional requests

Follow the RFC-style `Link` response header rather than synthesizing the final
page. Record page count, item count, and truncated/error state. De-duplicate by
stable repository ID because records can move between pages during a scan.

Store `ETag` and `Last-Modified` with the request identity and API version. Send
`If-None-Match` or `If-Modified-Since` for refreshes; a `304` reuses the prior
payload while updating retrieval provenance. Do not reuse a validator across a
different token scope, media type, API version, or query.

## GraphQL accelerator

GraphQL supports field-selective traversal, cursor pagination, global node IDs,
and a query-visible rate-limit object. It requires authentication. Every
connection supplies `first` or `last` from 1 through 100 and advances via
`pageInfo.endCursor`/`hasNextPage`.

Use GraphQL only when a configured server-side credential is present and a
query-cost budget has been reserved. Keep queries shallow, request only needed
fields, bound node counts, and fall back to REST on schema drift, partial errors,
timeouts, or exhausted cost. Do not make REST and GraphQL responses compete as
independent truths: normalize both into one versioned repository snapshot and
record the field-level source.

## Authentication

Anonymous REST is the default MVP mode for public repositories. The currently
documented primary limit is 60 requests/hour per originating IP, so anonymous
analysis is deliberately capped and progressively disclosed.

Optional credentials are server-side only:

- fine-grained personal access token with read-only metadata for developer use;
- GitHub App installation token for a future production integration;
- no browser storage, query-string transport, logging, or export of tokens.

Authenticated user REST requests generally receive 5,000 requests/hour;
GitHub App limits vary by installation and account. GraphQL uses a separate
point budget. Limits are operational observations, not permanent constants.

## Rate limits and resilience

Capture `x-ratelimit-limit`, `remaining`, `used`, `reset`, and `resource` from
every response. Prefer headers over polling `/rate_limit`. The worker:

1. reserves a request budget before each stage;
2. applies low concurrency and request de-duplication;
3. honors `Retry-After` and reset time;
4. uses bounded exponential backoff with jitter for retryable failures;
5. checkpoints partial results and resumes later;
6. surfaces degraded, sampled, and rate-limited states in the API and exports.

Secondary limits are partly undisclosed and can change without notice. Never
attempt to evade them; continuing while limited can cause an integration ban.

## Caching, storage, and terms

Cache immutable Git objects by object ID and API payloads by stable repository
ID, request identity, validator, and retrieval time. Retain only data needed for
analysis and evidence, support retention deletion, and identify cached data as a
snapshot rather than current GitHub state.

GitHub's Terms of Service, API terms, privacy statement, and acceptable-use
requirements are operational dependencies, not open-source licenses. A legal
review is required before public launch, especially for long-lived storage,
redistribution, and user-provided credentials. This document is engineering
guidance, not legal advice.

## Future monitoring

A GitHub App can subscribe to repository, push, release, pull-request, and
installation events to trigger incremental refreshes. Webhooks are future scope:
validate signatures, deduplicate delivery IDs, handle redelivery, and reconcile
periodically because delivery is not a complete historical record.

## Known gaps and validation tasks

- Confirm recursive fork visibility against recorded fixtures and at least two
  real networks; do not infer hidden or deleted members.
- Verify each normalized field against the pinned REST version's OpenAPI schema.
- Test rename, transfer, archived, disabled, deleted, empty, and oversized
  repositories with recorded responses.
- Re-check API version support, rate-limit guidance, and terms before release.
