# Operations

## Health model

- **Liveness:** process event loop responds; does not depend on downstreams.
- **Readiness:** API can reach PostgreSQL and serve its contract; worker can
  reach PostgreSQL/Redis and its Git-cache path.
- **Degraded:** optional GraphQL/token unavailable, quota low, or export storage
  impaired while safe read operations still work.

Expose only sanitized component state. Never return DSNs, tokens, paths containing
secrets, or raw upstream errors.

## Dashboards and alerts

Track by release and analysis version:

- request rate/latency/errors and SSE connections/replay lag;
- queue depth/oldest age, claim failures, duplicate deliveries, active workers;
- runs by stage/status, stage duration, retry/partial/cancel/resume counts;
- GitHub request count, cache hits, remaining/reset by resource, 403/429/5xx;
- Git fetch duration/bytes, subprocess timeout, quarantined store count;
- PostgreSQL connections/locks/slow queries/storage and Redis availability;
- Git/export disk usage, cleanup failures, and low-watermark admission rejects.

Alert on sustained API error rate, oldest-job age, no worker progress, migration
mismatch, repeated Git timeouts/corruption, quota exhaustion without waiting
state, database saturation, disk thresholds, retention failure, and secret-scan
findings.

## Runbooks

### GitHub quota exhausted

Confirm rate-limit headers and resource, stop new cost-bearing work, commit
affected runs as `partial` in the `waiting_for_quota` stage, honor reset/
`Retry-After`, reduce concurrency, and resume from checkpoints. Do not rotate
IPs/tokens to evade limits.

### Redis unavailable

Keep API reads available, reject or durably leave new work queued in PostgreSQL,
restore Redis, reconcile runnable job records idempotently, and confirm duplicate
delivery does not duplicate run events/results.

### Worker crash or stuck Git

Check heartbeat/stage age and sanitized process metadata. Terminate the bounded
process group, preserve the last committed checkpoint, inspect disk/quota, and
retry the work item. Quarantine a suspect network store; rebuild from recorded
heads rather than weakening Git safety controls.

### PostgreSQL unavailable

Fail readiness and stop job mutation. Do not continue using Redis as truth.
Restore connectivity or execute the tested database recovery plan, then reconcile
workers and verify event sequences/checkpoints before reopening admission.

### Disk pressure

Stop new deep analyses at the admission low-watermark. Expire exports and
unreferenced caches according to retention, never delete stores used by active
runs, and verify database references before/after cleanup. Increase capacity only
after identifying growth source.

### Suspected credential exposure

Disable/rotate the credential, stop affected workers, search sanitized audit
metadata without printing the secret, invalidate caches if authorization scope
changed, and review logs/events/exports. Record impact and preventive action.

### Bad release

Pause job claims, assess schema compatibility, roll application artifacts back or
forward-fix, then resume valid checkpoints under their original method version.
Do not reinterpret historical results with the new algorithm silently.

## Data lifecycle

The self-hosted defaults retain analysis rows for 30 days and generated exports
for 7 days. Operators may lengthen them for evidence preservation or shorten
them for data minimization, but must not remove objects cited by a retained run.
The MVP exposes retention as server configuration but does not schedule cleanup;
operator-run retention automation is deferred and there is no anonymous HTTP
deletion endpoint.

A future retention job must mark expired runs, remove derived exports, delete
run-scoped rows transactionally, and then delete only Git caches unreferenced by
retained/active runs. It must record counts, bytes, duration, and failures.
Backup/restore drills must include analysis rows, ordered events, export metadata,
and sealed Git evidence objects. Redis is reconstructable; evicted Git history
may not be recoverable after force-push, repository deletion, or loss of provider
access.

## Analysis support checklist

Given a run ID, inspect status/stage/attempt, last ordered event, checkpoint,
sampling/caps, provider quota snapshot, failed repositories, sealed heads,
method bundle, and worker release. Reproduce using fixture/recorded provider data
when possible. Never paste raw repository content or credentials into tickets.

## Routine cadence

- Daily: queue age, errors, quota, disk, retention, backup success.
- Weekly: restore sample, failed/partial-run review, slow stages, cache efficiency.
- Monthly: dependency/Git/image updates, capacity, abuse limits, access review.
- Quarterly/before release: GitHub API version/limits/terms, threat model,
  benchmark suite, disaster recovery, and real-repository smoke.
