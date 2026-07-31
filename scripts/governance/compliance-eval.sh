#!/usr/bin/env bash
# compliance-eval.sh — domain-blind mechanical rubric engine. CARRIED VERBATIM.
# Rubric line format:  HAS|<id>|<extended-regex>|<description>
#                      NOT|<id>|<extended-regex>|<description>
# The regex MAY contain '|'; the description MUST NOT (parsed as final field).
# Usage: compliance-eval.sh RUBRIC_FILE TARGET_FILE
set -euo pipefail
RUBRIC="${1:?usage: compliance-eval.sh RUBRIC TARGET}"
TARGET="${2:?usage: compliance-eval.sh RUBRIC TARGET}"
[ -f "$RUBRIC" ] || { echo "compliance-eval: rubric not found: $RUBRIC"; exit 2; }
[ -f "$TARGET" ] || { echo "compliance-eval: target not found: $TARGET"; exit 2; }
fail=0; n=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|\#*) continue;; esac
  kind=${line%%|*}; rest=${line#*|}
  [ "$kind" = "$line" ] && continue
  id=${rest%%|*}; rest=${rest#*|}
  desc=${rest##*|}; pat=${rest%|*}
  n=$((n+1))
  if grep -qiE "$pat" "$TARGET"; then present=1; else present=0; fi
  case "$kind" in
    HAS) if [ $present -eq 1 ]; then echo "PASS [$id] $desc"; else echo "FAIL [$id] $desc"; fail=1; fi;;
    NOT) if [ $present -eq 0 ]; then echo "PASS [$id] $desc"; else echo "FAIL [$id] $desc (forbidden pattern present)"; fail=1; fi;;
    *)   echo "compliance-eval: unknown check kind '$kind' (line $n)"; fail=1;;
  esac
done < "$RUBRIC"
unset line
echo "----"; echo "compliance-eval: $n checks against $(basename "$TARGET"); result=$([ $fail -eq 0 ] && echo PASS || echo FAIL)"
exit $fail
