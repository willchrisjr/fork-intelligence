# ADR 0001: Next.js, FastAPI, PostgreSQL, and Redis

Status: accepted
Date: 2026-07-13

## Context

The product needs an evidence-dense web interface, a typed HTTP contract,
long-running Python/Git analysis, durable checkpoint state, and asynchronous
work without premature distributed-service complexity.

## Decision

Use Next.js/TypeScript for the web application; FastAPI/Pydantic/SQLAlchemy for a
Python modular monolith exposing API and worker entrypoints; PostgreSQL for all
durable product state; and Redis for disposable job delivery/coordination.
Docker Compose provides PostgreSQL and Redis locally. OpenAPI is the contract
source. PostgreSQL, not Redis, stores run checkpoints and progress events.

## Consequences

The team operates two runtimes but uses each where its ecosystem is strongest.
Redis loss is recoverable. PostgreSQL is required in development and tests so a
SQLite fallback cannot hide integration drift. Module boundaries must remain
strict enough to extract services later if operational evidence justifies it.
