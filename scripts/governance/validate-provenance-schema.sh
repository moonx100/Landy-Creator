#!/usr/bin/env bash
# validate-provenance-schema.sh — enforce provenance.md (corpus half) + the
# statutes.status default from status-integrity.md, against the migrations.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
MIG="artifacts/landy-api/migrations/versions"
[ -d "$MIG" ] || { echo "SKIP provenance-schema: $MIG not found"; exit 0; }
fail=0
for col in source_url retrieved_date sha256 tier_basis; do
  if grep -rqIE "\b$col\b" "$MIG"; then echo "PASS: statutes column '$col' declared"
  else echo "FAIL: provenance/basis column '$col' missing from migrations"; fail=1; fi
done
if grep -rqIE "status[[:space:]]+TEXT.*DEFAULT[[:space:]]+'unverified'" "$MIG"; then
  echo "PASS: statutes.status defaults to 'unverified'"
else
  echo "FAIL: statutes.status must DEFAULT 'unverified' (operator-assigned only)"; fail=1
fi
if grep -rqIE "CHECK[[:space:]]*\(status[[:space:]]+IN" "$MIG"; then
  echo "PASS: statutes.status constrained by CHECK"
else
  echo "FAIL: statutes.status must carry a CHECK IN constraint"; fail=1
fi
if grep -rqIE "\bbasis\b" "$MIG"; then echo "PASS: citations.basis declared"
else echo "FAIL: citations.basis missing (statutory-vs-doctrinal labelling)"; fail=1; fi
exit $fail
