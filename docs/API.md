# API

FastAPI-generated OpenAPI is the executable contract. This document defines the
intended resource semantics; when it differs from generated OpenAPI, generated
OpenAPI and an explicit contract decision must be reconciled before release.
The product API is REST; GraphQL is only an internal authenticated GitHub
accelerator.

## Conventions

- Base path: `/api/v1`; JSON uses the generated schema's field names.
- IDs are opaque UUIDs. Times are UTC RFC 3339. Scores are 0–100; confidence and
  coverage are 0–1 unless the schema states otherwise.
- `Idempotency-Key` is required/recommended for create and command POSTs; replay
  returns the original compatible resource.
- List endpoints use opaque cursor pagination, stable sorting, filters, and a
  `next_cursor` indicator. Stable repository ID breaks sort ties.
- Responses expose analysis/configuration/method versions, provenance, depth,
  missing data, warnings, and sampling where relevant.
- Anonymous public analysis is supported. GitHub credentials are service-side
  configuration and are never accepted in request bodies.

The MVP is a single-tenant, self-hosted operator surface: anyone who can reach
the API is inside the trusted tenant boundary, including cancel/resume commands.
Do not expose it to an untrusted network. A public or multi-user deployment must
add authentication plus per-run mutation authorization; opaque analysis IDs are
not an authorization mechanism.

## Endpoints

| Method | Path                                                   | Purpose                                                        |
| ------ | ------------------------------------------------------ | -------------------------------------------------------------- |
| `POST` | `/api/v1/analyses`                                     | Validate and enqueue an analysis                               |
| `GET`  | `/api/v1/analyses/{analysis_id}`                       | Run status/configuration/sampling/quota                        |
| `GET`  | `/api/v1/analyses/{analysis_id}/events`                | SSE stream with ordered replay                                 |
| `GET`  | `/api/v1/analyses/{analysis_id}/overview`              | Counts, rankings, coverage, major directions                   |
| `GET`  | `/api/v1/analyses/{analysis_id}/forks`                 | Cursor-paginated/filterable/sortable fork rows                 |
| `GET`  | `/api/v1/analyses/{analysis_id}/forks/{repository_id}` | Fork detail, scores, classification, Git evidence              |
| `GET`  | `/api/v1/analyses/{analysis_id}/evolution`             | Bounded lineage/cluster graph plus disclosure                  |
| `GET`  | `/api/v1/analyses/{analysis_id}/clusters`              | Deterministic development-direction clusters                   |
| `POST` | `/api/v1/analyses/{analysis_id}/comparisons`           | Create comparison for upstream plus exactly two forks          |
| `GET`  | `/api/v1/comparisons/{comparison_id}`                  | Comparison status/result/evidence                              |
| `GET`  | `/api/v1/analyses/{analysis_id}/exports/{format}`      | `json`, `csv`, or `markdown` snapshot export                   |
| `POST` | `/api/v1/analyses/{analysis_id}/cancel`                | Request cooperative cancellation                               |
| `POST` | `/api/v1/analyses/{analysis_id}/resume`                | Resume retryable/cancelled/partial work from valid checkpoints |
| `GET`  | `/api/v1/health/live`                                  | Process liveness                                               |
| `GET`  | `/api/v1/health/ready`                                 | Sanitized dependency readiness                                 |

## Create analysis

```json
{
  "repository": "owner/repository",
  "mode": "explore",
  "configuration": {
    "analysis_depth": "structural",
    "max_forks": 250,
    "max_shortlist": 12
  }
}
```

Modes are `explore`, `successor`, `innovation`, and `compare`. Server maximums
override client values and are returned in the effective configuration/sampling
disclosure. Successful creation returns `202 Accepted` with the analysis
resource and links. An idempotent replay may return `200`/`202` consistently with
the existing state.

## Analysis state

Statuses are the canonical backend values: `queued`, `running`, `partial`,
`completed`, `failed`, `cancelling`, and `cancelled`. Quota exhaustion uses
`partial` status, a `waiting_for_quota` stage, and reset/retry metadata in the
quota snapshot; it is not a separate status value. Stages follow the pipeline but
clients treat new stage values as displayable unknowns. Progress is monotonic
within an attempt; a resumed attempt preserves prior events.

## SSE progress

Use `Accept: text/event-stream`. Each event has an integer/opaque sequence ID,
event type, stage, progress, occurrence time, and structured payload in each
JSON data object. Clients reconnect with
`Last-Event-ID`; the server replays committed events after that sequence, sends
heartbeats, and may require polling after the retention window. Events contain no
credentials or unbounded repository content.

Example shape:

```text
id: 42
data: {"type":"structural.repository_persisted","stage":"structural","progress":0.61,"created_at":"2026-07-13T20:00:00Z","payload":{"analyzed_forks":8}}
```

## Fork listing

Supported filters are search, classification, and analysis depth. Sort keys
cover score dimensions, unique commits/patches, confidence, and repository name.
A row reports its analysis depth and never substitutes zero for unavailable
structural metrics.

## Comparisons

`repository_ids` contains exactly three unique repositories from the same
analysis: the network root plus two forks. The result binds to explicit
branch/head SHAs where available and returns relationship, patch overlap,
composition, activity/score inputs, integration approximation, evidence IDs,
missing data, and version.

## Errors

Errors use RFC-style `application/problem+json` with stable extension fields:

```json
{
  "type": "https://fork-intelligence.local/problems/github_rate_limited",
  "title": "GitHub Rate Limited",
  "status": 503,
  "detail": "GitHub quota is exhausted; the analysis can resume after reset.",
  "instance": "/api/v1/analyses/opaque-id",
  "code": "github_rate_limited",
  "details": { "reset_at": "2026-07-13T21:00:00Z" },
  "request_id": "opaque-id"
}
```

Codes, not messages, drive clients. Expected statuses: `400` malformed request,
`404` absent resource without private-repository disclosure, `409` invalid state
transition, `413` request/config beyond limits, `422` schema validation, `429`
admission/rate limit with `Retry-After`, `502/503` retryable upstream/dependency,
and `500` sanitized internal error. The generated schema should expose whether a
condition is retryable consistently; raw Git/GitHub stderr is never returned.

## Exports and cache semantics

Exports are generated from a sealed run snapshot and include content type,
filename, hash/ETag, generation/version metadata, and retention. JSON is the full
machine-readable schema; CSV is safe for spreadsheet import; Markdown escapes
untrusted content. Analysis resources may use validators, but a refreshed run is
a new versioned snapshot rather than mutation hidden behind a cache response.
