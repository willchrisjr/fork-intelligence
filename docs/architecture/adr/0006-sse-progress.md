# ADR 0006: Durable Events over Server-Sent Events

Status: accepted
Date: 2026-07-13

## Context

Analysis is long-running and partial results must appear progressively. Updates
are server-to-browser, while cancel/resume are normal HTTP commands.

## Decision

Store ordered progress events durably in PostgreSQL and stream them over SSE.
Support `Last-Event-ID` replay and a polling endpoint as fallback. Redis may
notify workers/streamers but is not the event record.

## Consequences

SSE is simpler than bidirectional WebSockets and works with standard HTTP
infrastructure. The API must send heartbeats, bound replay pages, handle slow
clients, and document proxy buffering/timeouts. Cancellation remains an explicit
idempotent REST operation.
