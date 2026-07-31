#!/usr/bin/env bash
# validate-tenant-isolation.sh — enforce .claude/rules/tenant-isolation.md
# Primary isolation = explicit WHERE user_id predicates. RLS is defence-in-depth
# and is inert under the superuser DATABASE_URL (.agents/memory/rls-superuser-constraint.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
RT="artifacts/landy-api/landy/routes"
[ -d "$RT" ] || { echo "SKIP tenant-isolation: $RT not found"; exit 0; }
fail=0
TENANT='documents|document_versions|clauses|risk_flags|analysis_jobs|version_diffs|exports|redaction_mappings|suggested_edits|citations'

for f in "$RT"/*.py; do
  case "$(basename "$f")" in __init__.py|health.py|auth.py) continue;; esac
  if grep -qIE "$TENANT" "$f"; then
    if grep -qIE "user_id[[:space:]]*=[[:space:]]*:|user_id[[:space:]]*==|:uid|user_id=user|current_user" "$f"; then
      echo "PASS tenant-isolation: $(basename "$f") binds a user_id predicate"
    else
      echo "FAIL tenant-isolation: $(basename "$f") touches tenant tables with no user_id binding"
      fail=1
    fi
  fi
done

# RLS must not be asserted as the operative protection
rls=$(grep -rInE "RLS (is|provides|enforces).{0,30}(isolation|security|protection)|relies on (FORCE )?ROW LEVEL SECURITY|protected by RLS" \
      artifacts/landy-api 2>/dev/null || true)
if [ -n "$rls" ]; then
  echo "FAIL tenant-isolation: RLS asserted as operative protection (it is inert under a superuser role):"
  echo "$rls"; fail=1
else
  echo "PASS tenant-isolation: no RLS-as-primary-protection assertion"
fi

[ $fail -eq 0 ] && echo "PASS tenant-isolation"
exit $fail
