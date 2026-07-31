#!/usr/bin/env bash
# validate-tracked-changes.sh — enforce .claude/rules/tracked-changes-authenticity.md
# Real OOXML w:ins/w:del required; simulated colour/strikethrough redlines forbidden.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
EXP="artifacts/landy-api/landy/export"
[ -d "$EXP" ] || { echo "SKIP tracked-changes: $EXP not found"; exit 0; }
fail=0
if grep -rIqE "w:ins" "$EXP" && grep -rIqE "w:del" "$EXP"; then
  echo "PASS tracked-changes: w:ins and w:del revision markup present"
else
  echo "FAIL tracked-changes: export lacks real OOXML w:ins/w:del revision markup"; fail=1
fi
if grep -rIqE "w:delText" "$EXP"; then
  echo "PASS tracked-changes: w:delText used for deleted runs"
else
  echo "FAIL tracked-changes: deleted text must live in w:delText per OOXML spec"; fail=1
fi
if grep -rIqE "w:author" "$EXP" && grep -rIqE "w:date" "$EXP"; then
  echo "PASS tracked-changes: revisions attributed (w:author + w:date)"
else
  echo "FAIL tracked-changes: revisions must carry w:author and w:date"; fail=1
fi
# anti-pattern: formatting standing in for revision markup
sim=$(grep -rInE "w:strike|w:highlight|<w:color[^>]*(FF0000|red)" "$EXP" || true)
if [ -n "$sim" ]; then
  echo "FAIL tracked-changes: simulated-redline formatting in an export generator:"
  echo "$sim"; fail=1
else
  echo "PASS tracked-changes: no simulated strikethrough/colour redline"
fi
[ $fail -eq 0 ] && echo "PASS tracked-changes-authenticity"
exit $fail
