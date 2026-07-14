# Decisions

- **D001 - Modular monolith:** one Python distribution exposes separate API and
  worker entrypoints to keep boundaries clear without premature services.
- **D002 - Production-like local infrastructure:** Docker Compose runs
  PostgreSQL and Redis; no SQLite application fallback hides integration drift.
- **D003 - Durable progress:** PostgreSQL stores checkpoints and ordered events;
  Redis loss may delay work but cannot erase analysis state.
- **D004 - Deterministic core:** scoring, classification, clustering, and
  evidence generation function without an LLM. Live AI is deferred.
- **D005 - Bounded analysis:** metadata census is broad, Git analysis is
  shortlisted, and every cap or incomplete stage is disclosed.
- **D006 - Git isolation:** use bare network stores and exact namespaced refs;
  never check out or execute analyzed repositories.
- **D007 - Visualization:** lineage uses a stable layered layout; cluster mode
  may use a bounded force layout. Both have synchronized table alternatives.
- **D008 - Docker runtime:** Docker Desktop could not complete its privileged
  helper installation non-interactively, so Colima plus Docker CLI/Compose is
  the validated local runtime with the same Compose contract.
- **D009 - Configuration contract:** backend variables use the
  `FORK_INTELLIGENCE_` prefix; the browser uses a same-origin `/api/v1` proxy so
  credentials and cross-origin policy remain server-side.
- **D010 - MVP trust boundary:** the self-hosted MVP is a trusted single-tenant
  operator surface. Opaque run IDs are not authorization; public or multi-user
  deployment requires authentication and per-run mutation controls.
- **D011 - Admission and recovery:** PostgreSQL queue state is authoritative;
  queued jobs may be safely redispatched after Redis message loss, while
  per-client request throttles, active-run caps, per-repository serialization,
  and a disk low-watermark gate bound anonymous work.
- **D012 - Git resource failure:** stdout/stderr are streamed into bounded
  buffers, timeout/resource failure terminates the full process group, compare
  commands share one deadline, and an oversized network store is quarantined
  for operator cleanup rather than reused.
- **D013 - Sealed exports:** exports are generated only from completed, failed,
  cancelled, or quota-partial checkpoints and then remain immutable for their
  analysis version, yielding stable content hashes and ETags.
- **D014 - Browser fallback:** the in-app browser runtime was unusable on this
  host, so the standalone Playwright workflow is the accepted browser evidence;
  macOS browser processes require execution outside the filesystem sandbox.
