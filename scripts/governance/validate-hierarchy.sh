#!/usr/bin/env bash
# validate-hierarchy.sh — enforce .claude/rules/statutory-vs-doctrinal.md
# ADAPTED: Creator has no ruleset.json. Checks the schema carries the basis
# fields and that no tier rank literal is hardcoded in application code.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
API="artifacts/landy-api"
[ -d "$API" ] || { echo "SKIP hierarchy: $API not found"; exit 0; }
fail=0
if grep -rqIE "tier_basis" "$API/migrations" 2>/dev/null; then
  echo "PASS hierarchy: tier_basis present in schema"
else
  echo "FAIL hierarchy: statutes.tier_basis missing — tiers cannot be classified"; fail=1
fi
hits=$(grep -rInE "tier_rank[[:space:]]*=[[:space:]]*[0-9]" "$API/landy" 2>/dev/null || true)
if [ -n "$hits" ]; then
  echo "FAIL hierarchy: hardcoded tier_rank literal in application code:"; echo "$hits"; fail=1
else
  echo "PASS hierarchy: no hardcoded tier_rank literals in application code"
fi
# doctrinal ranking must not be asserted as statutory
doc=$(grep -rInE "(POJK|SEOJK).{0,40}(lebih tinggi|lebih rendah|rank(s)? (above|below))" "$API" 2>/dev/null || true)
if [ -n "$doc" ]; then
  echo "FAIL hierarchy: POJK/SEOJK relative rank asserted (not codified — doctrinal/open):"; echo "$doc"; fail=1
else
  echo "PASS hierarchy: no uncodified POJK/SEOJK ranking asserted"
fi
[ $fail -eq 0 ] && echo "PASS hierarchy"
exit $fail
