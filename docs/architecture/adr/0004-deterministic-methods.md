# ADR 0004: Deterministic Scoring, Classification, and Clustering

Status: accepted
Date: 2026-07-13

## Context

Users need reproducible rankings and development directions. One universal score
or opaque semantic model would conflate intent and make conclusions difficult to
audit.

## Decision

Keep raw metrics separate from versioned score snapshots. Publish distinct
dimensions and named profiles with weights, confidence, coverage, and evidence.
Classifications use deterministic reason rules. Clustering uses a versioned
feature schema and stable average-link agglomerative clustering over cosine
distance; stable repository IDs break ties. Labels are heuristic terms extracted
from representative paths, dependencies, and commit text.

## Consequences

Results are reproducible and testable but labels may be less fluent than a model.
Thresholds and normalizers require fixture calibration. Any future method change
creates a new version and snapshots rather than rewriting historical results.
