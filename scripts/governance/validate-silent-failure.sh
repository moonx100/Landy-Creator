#!/usr/bin/env bash
# validate-silent-failure.sh — enforce .claude/rules/silent-failure.md
# ADAPTED from landy-workspace: re-pointed from ingest/rag to the Creator API,
# and extended with the reassuring-default check (the Creator money-path failure).
#
# PRAGMA: a legitimate fallback chain that ultimately raises may mark its
# swallowing handler with an inline comment:
#     except ValueError:  # silent-failure-ok: fallback chain, raises at end
# Every pragma needs MV's sign-off in the PR.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
API="artifacts/landy-api"
[ -d "$API" ] || { echo "SKIP silent-failure: $API not found"; exit 0; }
fail=0

# 1. bare excepts (advisory — must log + surface)
bare=$(grep -rInE "except[[:space:]]*:[[:space:]]*$" "$API" --include="*.py" 2>/dev/null \
       | grep -v "silent-failure-ok" || true)
if [ -n "$bare" ]; then echo "WARN silent-failure: bare 'except:' (must log + surface):"; echo "$bare"; fi

# 2. except ... : pass — flagged unless the handler carries the pragma
#    (checks the except line and the pass line for the marker)
sp=""
while IFS= read -r hit; do
  f="${hit%%:*}"; rest="${hit#*:}"; ln="${rest%%:*}"
  exline=$(sed -n "$((ln-1))p" "$f" 2>/dev/null)
  passline=$(sed -n "${ln}p" "$f" 2>/dev/null)
  case "$exline$passline" in *silent-failure-ok*) continue;; esac
  sp="$sp$f:$ln: $(echo "$exline" | sed 's/^[[:space:]]*//') -> pass"$'\n'
done < <(grep -rInE "^[[:space:]]*pass[[:space:]]*$" "$API" --include="*.py" 2>/dev/null \
         | while IFS= read -r l; do
             f="${l%%:*}"; r="${l#*:}"; n="${r%%:*}"
             prev=$(sed -n "$((n-1))p" "$f" 2>/dev/null)
             case "$prev" in *except*) echo "$f:$n:";; esac
           done)
if [ -n "$sp" ]; then
  echo "FAIL silent-failure: 'except ...: pass' swallows a failure (add a pragma if it is a raising fallback chain):"
  printf '%s' "$sp"; fail=1
else
  echo "PASS silent-failure: no unpragma'd except-pass"
fi

# 3. reassuring defaults on failure paths — the Creator money-path failure mode
def=$(grep -rInE "return[[:space:]]*\[?\(?[\"']immaterial[\"']|\([\"']immaterial[\"'],[[:space:]]*[\"']" \
      "$API" --include="*.py" 2>/dev/null || true)
if [ -n "$def" ]; then
  echo "FAIL silent-failure: 'immaterial' written as a fallback classification"
  echo "  (a failed classification must surface as needs_review, not as a clean result):"
  echo "$def"; fail=1
else
  echo "PASS silent-failure: no 'immaterial' fallback default"
fi

# 4. a surfaced review/unavailable state must exist in the domain vocabulary
#    (extended 2026-08-02 with the LC-41 vocabulary actually implemented:
#    classification_status + parse_ok/parse_status)
if grep -rIqE "needs_review|classification_unavailable|review_required|analysis_incomplete|classification_status|parse_ok|parse_status" \
   "$API" --include="*.py" 2>/dev/null; then
  echo "PASS silent-failure: a surfaced review/unavailable state exists"
else
  echo "FAIL silent-failure: no needs_review/unavailable state in the domain vocabulary — failures have nowhere honest to land"
  fail=1
fi

[ $fail -eq 0 ] && echo "PASS silent-failure"
exit $fail
