#!/usr/bin/env bash
# validate-extraction-coverage.sh — enforce .claude/rules/extraction-coverage.md
# extraction_ok must rest on a coverage floor/ratio, not on non-emptiness alone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
EX="artifacts/landy-api/landy/extraction.py"
[ -f "$EX" ] || { echo "SKIP extraction-coverage: $EX not found"; exit 0; }
fail=0
# 1. a named coverage threshold constant must exist
if grep -qE "_MIN_(CHARS|EXTRACT|COVERAGE)|_COVERAGE_|MIN_CHARS_PER_(PAGE|PARA)" "$EX"; then
  echo "PASS extraction-coverage: coverage threshold constant present"
else
  echo "FAIL extraction-coverage: no coverage threshold constant (e.g. _MIN_CHARS, _MIN_CHARS_PER_PAGE)"
  fail=1
fi
# 2. a ratio/floor comparison against an independent size signal must exist
if grep -qE "len\(.*\)[[:space:]]*[<>]=?[[:space:]]*_?(MIN|COVERAGE)|/[[:space:]]*(page_count|len\(pages\)|len\(paras\))" "$EX"; then
  echo "PASS extraction-coverage: floor/ratio comparison present"
else
  echo "FAIL extraction-coverage: no floor or per-page/per-element ratio check"
  fail=1
fi
# 3. bare non-emptiness used as the success test
bare=$(grep -nE "(ok|extraction_ok)[[:space:]]*=[[:space:]]*bool\([^)]*strip\(\)\)" "$EX" || true)
if [ -n "$bare" ]; then
  echo "FAIL extraction-coverage: extraction_ok set from bare non-emptiness test:"
  echo "$bare"
  fail=1
fi
[ $fail -eq 0 ] && echo "PASS extraction-coverage"
exit $fail
