#!/usr/bin/env bash
# validate-all.sh — run every LANDY Creator gate. Exit nonzero if any fails.
# Run at task close and in CI.
#
# NOTE: some gates fail on a clean checkout today. Those are REAL, LOGGED
# findings (.agents/memory/), not broken validators. Fix the code or record why
# the gap stands — never relax a validator to make the suite green.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
rc=0
run() { echo "== $1 =="; bash "scripts/governance/$1" || rc=1; echo; }

# shape / structure (domain-blind)
run validate-gate-first.sh
run validate-bridge-health.sh
run validate-memory-sync.sh
run validate-enforcement-registry.sh
run validate-index-sync.sh

# secrets first — cheapest gate, worst failure
run validate-secrets-hygiene.sh

# Creator money-path
run validate-redaction-before-inference.sh
run validate-extraction-coverage.sh
run validate-tracked-changes.sh
run validate-legal-advice-framing.sh
run validate-tenant-isolation.sh
run validate-silent-failure.sh
run validate-silent-failure-web.sh

# carried corpus/authority discipline
run validate-provenance-schema.sh
run validate-status-integrity.sh
run validate-hierarchy.sh

# dormant
run validate-source-access.sh

echo "=== landy-creator validate-all: $([ $rc -eq 0 ] && echo ALL PASS || echo FAILURES) ==="
exit $rc
