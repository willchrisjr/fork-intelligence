# Deployment

## Supported topology

Deploy four independently scalable process roles from the monorepo:

- Next.js web;
- FastAPI API;
- Python worker;
- PostgreSQL and Redis managed services (or Compose locally).

API and worker use the same immutable Python artifact and configuration schema.
The worker mounts a persistent Git-cache volume; MVP export content and hashes
are stored durably in PostgreSQL. A future large-export deployment may add object
storage without changing export identity. Redis is not durable analysis storage.

## Required configuration

Exact variable names are defined by `.env.example` and application settings.
Production must provide:

- PostgreSQL URL and Redis URL;
- public web/API origins and strict CORS allowlist;
- Git cache/export locations and retention/cap values;
- GitHub REST API version (verified baseline `2026-03-10`);
- optional server-side GitHub token or future GitHub App credentials;
- log level, release/analysis version, and process concurrency;
- secret-store references, never literal secrets in manifests.

No OpenAI/AI provider key is required or used in the MVP.

## Local development

Use the root README/package scripts as the command source. The intended sequence
is: copy `.env.example`, start PostgreSQL/Redis with Docker Compose, install locked
Node/Python dependencies, run Alembic migrations, then start web, API, and worker.
Apple Silicon macOS and Linux are supported targets. A non-Docker application
workflow may connect to compatible local PostgreSQL/Redis but does not use SQLite.

## Release process

1. Verify clean source and lockfiles; run format, lint, type, unit, integration,
   Git-fixture, contract, end-to-end, build, and security checks.
2. Build immutable artifacts with revision/version metadata; scan dependencies,
   secrets, and images.
3. Back up PostgreSQL and test restore. Review migration upgrade/downgrade or
   forward-fix strategy on a production-shaped copy.
4. Deploy migrations as a singleton job compatible with old and new application
   versions; prefer expand/migrate/contract changes.
5. Deploy API/web, then workers with low initial concurrency. Verify liveness,
   readiness, SSE proxy behavior, queue claim, and a synthetic analysis.
6. Increase traffic/concurrency while watching errors, quota, DB, queue, disk,
   and event lag.
7. Record release revision, migration head, configuration/method bundle, checks,
   operator, and rollback decision point.

## Production hardening

- TLS at every external boundary; private DB/Redis networks and authenticated
  Redis where supported.
- Non-root application containers; worker-only write access to its Git-cache
  volume; least-privilege service identities. A read-only root filesystem is a
  recommended deployment-layer control, not enabled by the local Compose file.
- Resource limits and process sandboxing for Git workers; no Docker socket.
- Encrypted backups, key rotation, audit logs, and a reviewed retention job
  before production data-lifecycle automation is enabled.
- Proxy buffering disabled for SSE, with heartbeats and timeouts tested.
- Separate worker pools/concurrency budgets if deep Git work harms metadata work.

## Rollback and compatibility

Application rollback is allowed only while the prior version is compatible with
the migrated schema. Never roll back by deleting user analysis data. Pause job
claims before incompatible worker changes, drain or safely checkpoint active work,
and retain method versions so old runs remain readable. Redis can be flushed and
reconstructed from PostgreSQL. Unsealed Git caches can be quarantined and rebuilt
on a best-effort basis; objects cited by retained evidence must be preserved
because provider history can disappear. PostgreSQL recovery uses tested backups
and point-in-time recovery where available.

## Deployment validation

Confirm health/readiness, migration head, API OpenAPI contract, web/API origin,
SSE replay, job create/cancel/resume, DB persistence across Redis restart, cache
write/cleanup, all exports, no-secret logs, and one opt-in public-repository smoke
analysis. Record failures and residual risk; do not claim release readiness from
container startup alone.
