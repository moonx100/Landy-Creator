#!/usr/bin/env bash
# validate-silent-failure-web.sh — enforce .claude/rules/silent-failure.md on
# the TypeScript render layer (LC-38, authored 2026-08-02 with MV sign-off via
# the LC-41 plan approval).
#
# The frontend twin of the reassuring-default bug: a config-map lookup that
# coalesces an unrecognised state into a benign default —
#     MATERIALITY_CONFIG[row.materiality] ?? MATERIALITY_CONFIG.immaterial
# renders a failed classification as quiet grey "not material". The required
# shape is a TOTAL mapping (a typed Record + an explicit derivation function)
# whose unknown branch is a loud, visible state.
#
# Detection: a bracketed member/index lookup immediately followed by `??`.
# Scalar coalescing (`x ?? 0`, `foo() ?? "-"`) has no preceding `]` and is not
# flagged. Cosmetic label fallbacks may be marked with an inline pragma:
#     {DOMAIN_LABELS[flag.domain] ?? flag.domain} // silent-failure-ok: cosmetic label
# Cosmetic = the fallback renders the RAW KEY itself (visible, not a
# misclassification). Falling back to a *different config entry* is never
# cosmetic. Every pragma needs MV's sign-off in the PR.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
WEB="artifacts/landy-web/src"
MOBILE="artifacts/landy-mobile"
fail=0

check_tree() {
  local tree="$1"
  [ -d "$tree" ] || return 0
  # lookup-into-map followed by ?? — the misclassifying-fallback shape.
  # Allow the raw-key cosmetic form `X[k] ?? k` only when pragma'd.
  local hits
  hits=$(grep -rInE "\][[:space:]]*\?\?" "$tree" \
           --include="*.ts" --include="*.tsx" 2>/dev/null \
         | grep -v "silent-failure-ok" || true)
  if [ -n "$hits" ]; then
    echo "FAIL silent-failure-web ($tree): map-lookup coalesced into a default."
    echo "  An unrecognised state must render loudly (total mapping), never as a benign default:"
    echo "$hits"
    fail=1
  else
    echo "PASS silent-failure-web ($tree): no unpragma'd map-lookup ?? fallback"
  fi
}

check_tree "$WEB"
check_tree "$MOBILE"

# The all-clear sentences must be gated: every file that renders one of the
# absence claims must also reference review_complete somewhere.
for f in $(grep -rIlE "Tidak ada perubahan material|Tidak ada temuan risiko" "$WEB" \
             --include="*.tsx" 2>/dev/null || true); do
  case "$f" in *Demo*) continue;; esac  # demo pages render hardcoded copy
  if ! grep -q "review_complete" "$f"; then
    echo "FAIL silent-failure-web: $f renders an all-clear claim without consulting review_complete"
    fail=1
  else
    echo "PASS silent-failure-web: $f gates its all-clear claim on review_complete"
  fi
done

[ $fail -eq 0 ] && echo "PASS silent-failure-web"
exit $fail
