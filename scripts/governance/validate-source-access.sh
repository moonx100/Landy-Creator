#!/usr/bin/env bash
# validate-source-access.sh — enforce .claude/rules/source-access.md (DORMANT rule)
# Creator does not scrape. This arms the denylist ahead of the mini-corpus build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
DENY="scripts/governance/source-denylist.txt"
fail=0
if [ -f "$DENY" ] && [ -d artifacts ]; then
  while read -r host; do
    case "$host" in ''|\#*) continue;; esac
    hits=$(grep -rInF "$host" artifacts --include="*.py" --include="*.ts" --include="*.tsx" 2>/dev/null || true)
    if [ -n "$hits" ]; then echo "FAIL source-access: denylisted host '$host' referenced:"; echo "$hits"; fail=1; fi
  done < "$DENY"
fi
[ $fail -eq 0 ] && echo "PASS source-access: no denylisted host referenced (rule dormant — Creator does not scrape)"
exit $fail
