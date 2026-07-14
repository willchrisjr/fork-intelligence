# ADR 0003: Safe Bare Git Network Store

Status: accepted
Date: 2026-07-13

## Context

Independent clones duplicate objects and increase attack surface. Commit-graph
and patch analysis needs shared complete history without executing repository
content.

## Decision

Use one bare Git store per network with exact analyzer refs under
`refs/forks/<repository-id>/<encoded-branch>`. Fetch canonical allowlisted HTTPS
GitHub remotes through fixed argv arrays, start with `blob:none`, and materialize
bounded blobs only for deep analysis. Disable hooks, unsafe protocols, recursive
submodules, credential prompts, and inherited system/user configuration. Never
checkout or execute analyzed content. Do not use alternates in the MVP.

## Consequences

Objects are efficiently shared and refs preserve fork identity. The worker must
serialize ref mutation, seal run snapshots, enforce resource limits, and manage
GC/retention carefully. Full structural conclusions require complete history;
shallow previews must be labeled and deepened.
