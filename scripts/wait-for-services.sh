#!/usr/bin/env bash
set -euo pipefail

for _ in $(seq 1 60); do
  if docker-compose exec -T postgres pg_isready \
      -U fork_intelligence -d fork_intelligence >/dev/null 2>&1 && \
     docker-compose exec -T redis redis-cli ping 2>/dev/null | grep -q '^PONG$'; then
    exit 0
  fi
  sleep 1
done

echo "PostgreSQL and Redis did not become ready within 60 seconds." >&2
exit 1
