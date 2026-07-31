#!/usr/bin/env bash
# validate-redaction-before-inference.sh — enforce .claude/rules/redact-before-inference.md
# Enumerate every chat_complete( call site; each enclosing module must import
# landy.redaction.redact, or be listed with justification in redaction-exempt.txt.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
API="artifacts/landy-api"
EXEMPT="scripts/governance/redaction-exempt.txt"
[ -d "$API" ] || { echo "SKIP redaction: $API not found"; exit 0; }
fail=0
# call sites = chat_complete( that is not the abstract/def declaration
mapfile -t sites < <(grep -rIln "chat_complete(" "$API" --include="*.py" 2>/dev/null \
                     | grep -v "/llm.py$" | sort -u)
[ ${#sites[@]} -eq 0 ] && { echo "PASS redaction: no chat_complete call sites"; exit 0; }
for m in "${sites[@]}"; do
  if grep -qE "from[[:space:]]+landy\.redaction[[:space:]]+import|import[[:space:]]+landy\.redaction|redaction\.redact|[^_a-z]redact\(" "$m"; then
    echo "PASS redaction: $m (redact reachable in module)"
  elif [ -f "$EXEMPT" ] && grep -qF "$m" "$EXEMPT"; then
    echo "WARN redaction: $m EXEMPT (justification on file — re-verify)"
  else
    echo "FAIL redaction: $m calls chat_complete() with no redact() in module and no exemption"
    fail=1
  fi
done
[ $fail -eq 0 ] && echo "PASS redaction-before-inference: all call sites covered"
exit $fail
