#!/usr/bin/env bash
# validate-status-integrity.sh — enforce .claude/rules/status-integrity.md
# ADAPTED: re-pointed from ingest/rag/graph to artifacts/landy-api.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
API="artifacts/landy-api"
[ -d "$API" ] || { echo "SKIP status-integrity: $API not found"; exit 0; }
ALLOWLIST="scripts/governance/status-integrity-allowlist.txt"
allow_re='landy/admin\.py|operator_status\.py'
if [ -f "$ALLOWLIST" ]; then
  while read -r line; do
    case "$line" in ''|\#*) continue;; esac
    allow_re="$allow_re|$line"
  done < "$ALLOWLIST"
fi
# forbidden: writing a verified status value; read-only comparisons (==) not flagged
hits=$(grep -rInE "status['\"]?\]?[[:space:]]*[:=][^=]*['\"](in_force|revoked|partially_valid)['\"]" \
      "$API" --include="*.py" 2>/dev/null | grep -vE "$allow_re" | grep -viE "CHECK[[:space:]]*\(status[[:space:]]+IN" || true)
if [ -n "$hits" ]; then
  echo "FAIL status-integrity: verified status written outside the operator entrypoint:"
  echo "$hits"; exit 1
fi
echo "PASS status-integrity: no forbidden status writes (allowlist: $allow_re)"
