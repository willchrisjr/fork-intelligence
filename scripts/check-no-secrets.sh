#!/usr/bin/env bash
set -euo pipefail

if git grep -n -I -E '(ghp_|github_pat_|sk-proj-|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY)' -- ':!scripts/check-no-secrets.sh'; then
  echo "Potential secret material detected in tracked content." >&2
  exit 1
fi

echo "No known secret patterns found in tracked content."
