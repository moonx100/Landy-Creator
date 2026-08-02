#!/usr/bin/env bash
# validate-index-sync.sh — wraps `index-headings.ts --check` (governance
# apparatus, 2026-08-02). Fails the build if any registered *-INDEX.md has
# drifted from its source, or is missing entirely.
#
# Registration is a judgment call (see scripts/src/index-headings.ts header
# and scripts/index-registry.json's registered_when notes), not a hard
# line-count gate — this validator just enforces "whatever IS registered
# stays in sync."
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"

[ -f "scripts/index-registry.json" ] || {
  echo "validate-index-sync: no scripts/index-registry.json (skip)"; exit 0;
}
[ -f "scripts/src/index-headings.ts" ] || {
  echo "validate-index-sync: no generator script (skip)"; exit 0;
}

# node_modules may not be installed in every environment that runs
# validate-all.sh (e.g. a fresh checkout before `pnpm install`). Degrade to a
# skip with a clear message rather than a confusing tool-not-found failure.
if ! command -v npx >/dev/null 2>&1; then
  echo "validate-index-sync: npx not available (skip — install Node to enforce this gate)"
  exit 0
fi
if [ ! -d "node_modules" ] && [ ! -d "scripts/node_modules" ]; then
  echo "validate-index-sync: node_modules not installed (skip — run pnpm install to enforce this gate)"
  exit 0
fi

cd scripts
if npx --yes --silent tsx ./src/index-headings.ts --check; then
  echo "PASS index-sync"
  exit 0
else
  echo "FAIL index-sync: a registered INDEX is stale — regenerate with"
  echo "  cd scripts && npx tsx ./src/index-headings.ts"
  exit 1
fi
