# ADR 0005: No Live AI in the MVP

Status: accepted
Date: 2026-07-13

## Context

The product brief allows optional AI enrichment, but the core must work without
an API key and repository content is prompt-injection input. Live AI adds cost,
latency, privacy, evidence-validation, and operational complexity before the
deterministic evidence model is proven.

## Decision

Do not connect or call a live AI provider in the MVP. All scoring,
classification, cluster membership, labels, summaries, and explanations are
deterministic and evidence-backed. Keep a narrow provider protocol solely as a
disabled test seam, exercised by a deterministic fake provider. It accepts no
credential and no production code path may select a live provider.

## Consequences

There is no AI credential, usage limit, model metadata, or prompt surface to
operate in the MVP. The disabled setting is not an extension point available to
operators. Heuristic summaries must use cautious language. Introducing AI later
requires a new ADR and threat-model review with structured bounded evidence,
evidence-ID validation, usage controls, and a deterministic fallback.
