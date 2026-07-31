#!/usr/bin/env bash
# validate-gate-first.sh — domain-blind rule-shape validator. CARRIED VERBATIM.
# Every binding rule under .claude/rules/ must carry FAIL condition + WHERE-checked
# + Enforcement strength. Opt out with: <!-- gate-first-exempt: reason -->
# Usage: validate-gate-first.sh [RULES_DIR]   (default: .claude/rules)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
DIR="${1:-.claude/rules}"
fail=0
shopt -s nullglob
files=("$DIR"/*.md)
if [ ${#files[@]} -eq 0 ]; then
  echo "validate-gate-first: no rule files in $DIR (nothing to check)"; exit 0
fi
for f in "${files[@]}"; do
  if grep -qiE '^<!--[[:space:]]*gate-first-exempt:' "$f"; then
    echo "SKIP (exempt): $f"; continue
  fi
  miss=()
  grep -qiE 'FAIL condition:'       "$f" || miss+=("FAIL condition")
  grep -qiE 'WHERE-checked:'        "$f" || miss+=("WHERE-checked")
  grep -qiE 'Enforcement strength:' "$f" || miss+=("Enforcement strength")
  if [ ${#miss[@]} -eq 0 ]; then echo "PASS: $f"
  else echo "FAIL: $f  — missing: ${miss[*]}"; fail=1; fi
done
exit $fail
