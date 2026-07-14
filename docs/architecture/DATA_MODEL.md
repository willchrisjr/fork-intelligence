# Data Model

PostgreSQL is the durable source of truth. JSONB may preserve raw provider data,
but all queried identity, state, score, and provenance fields are normalized.
All tables use timestamps and immutable external IDs where available.

## Core entities

### RepositoryNetwork

`id`, root repository ID, provider/network identity, first discovered time, last
refreshed time, and census completeness metadata. A network has many repositories
and runs.

### Repository

GitHub numeric ID (unique), node ID, owner, name, canonical URL, parent ID,
source/root ID, default branch, archived/disabled state, visibility, license,
language, size, provider timestamps, first/last seen, and tombstone status.
Owner/name history is preserved separately so transfers do not create new
identities.

### RepositorySnapshot

Repository + analysis run, raw provider payload, normalized metadata, ETag,
source API/version, retrieval time, coverage, and warnings. Snapshots are
immutable after their stage commits.

### Branch

Repository, exact provider name, encoded analyzer ref, head SHA, default flag,
last commit time, priority, included state/reason, analysis depth, and retrieval
time. `(run, repository, branch_name, head_sha)` identifies the observation.

### AnalysisRun

Requested repository, resolved network, status, stage, progress, mode,
configuration snapshot, analysis/method bundle version, attempt, timestamps,
cancellation time, rate-limit snapshot, sampling disclosures, and normalized
error. Status transitions are validated state-machine events.

### AnalysisCheckpoint and ProgressEvent

Checkpoint records stage/work-item completion and input/output hashes. Events
carry a monotonically increasing per-run sequence, type, stage, progress,
message code, structured detail, and creation time. The event sequence backs SSE
replay and polling.

## Git and comparison entities

### CommitRecord and CommitMembership

Store only evidence-needed commit metadata: SHA, parents, author/committer times,
bounded message digest/summary, and provider URL. Membership maps a commit to a
run/repository/branch head without duplicating Git objects.

### PatchFingerprint

Method/version, stable patch ID, normalized hash where used, source commit(s),
parent policy, changed-path summary, and exact Git/diff options. Many commits can
map to one fingerprint; equality level and confidence are explicit.

### RepositoryComparison

Run, left/right repository and branches/heads, merge base(s), ahead/behind,
unique/shared commits, patch overlap, file/directory composition, dependency
differences, conflict approximation with method/version, state, and warnings.

### ChangeArtifact

A typed unit (`commit`, `patch`, `file_group`, `dependency_change`, `release`,
or `change_family`) with structured payload, provenance, method version, and
links to lower-level artifacts.

## Interpretation entities

### EvidenceItem

Type, provider/source, URL, repository, commit/path/release reference, structured
payload, retrieval/calculation time, provenance kind (`provider`, `calculated`,
`heuristic`), and content digest. Evidence is immutable and referenced by ID.

### MetricObservation

Repository/run, metric name, raw value/unit, source evidence IDs, availability,
measurement time, and normalizer version. Raw metrics are never overwritten by
scores.

### ScoreSnapshot

Repository/run, dimension/profile, normalized value, raw inputs, weights,
score version, confidence, coverage, missing inputs, depth, and calculation time.

### Classification

Repository/run, label, confidence, ordered reason codes, evidence IDs,
classification version, missing evidence, and depth. Labels are not mutable
repository attributes; they are run-specific conclusions.

### DevelopmentCluster

Run, algorithm/version, feature schema/version, member repositories, centroid or
representative vector, deterministic label/summary, representative artifacts,
confidence, and labeling method. Feature vectors may use PostgreSQL arrays/JSONB;
`pgvector` is not included unless actual vector search is introduced.

### ExportArtifact

Run, format, configuration/provenance snapshot, storage key, content hash,
generation version, size, created/expiry times, and state.

## Constraints and retention

- Foreign keys prevent evidence, scores, and comparisons from escaping their
  source run.
- Unique idempotency constraints prevent duplicate active runs and duplicate
  progress sequences.
- Provider payloads and untrusted text have length limits; rendered text is
  escaped/sanitized.
- Tokens are never persisted in analysis tables, events, logs, or exports.
- Deleting an expired run cascades derived database artifacts and schedules its
  export deletion; Git network caches are removed only when no retained run
  references them.
- Algorithm versions are append-only. Recalculation creates a new snapshot.
