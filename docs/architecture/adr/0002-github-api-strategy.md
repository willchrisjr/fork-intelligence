# ADR 0002: Anonymous REST Baseline with GraphQL Acceleration

Status: accepted
Date: 2026-07-13

## Context

The MVP must analyze public repositories without requiring credentials while
remaining efficient when a scoped credential is available. GraphQL requires
authentication and has cost/node limits; REST fork listing supports anonymous
public access.

## Decision

Make versioned GitHub REST the required correctness path, including anonymous
mode. Add authenticated GraphQL only as an optional metadata-batching accelerator.
Normalize either path into the same field-provenance model and fall back to REST
on GraphQL partial errors, budget exhaustion, timeout, or schema drift. Pin the
REST API version via configuration and revalidate it before release.

## Consequences

Anonymous runs are constrained by the shared 60-request/hour IP budget and must
be capped, cached, and transparent. The worker needs two provider clients and
contract fixtures, but results do not depend on a token or GraphQL availability.
