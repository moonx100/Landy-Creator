#!/usr/bin/env bash
# validate-enforcement-registry.sh — drift guard for the Enforcement Registry
# table in .claude/rules/README.md (added 2026-08-02, governance apparatus).
#
# Two checks, both against the registry table's own text:
#   1. Every rule file under .claude/rules/*.md (excluding README.md itself)
#      is named somewhere in the registry table.
#   2. Every validator script under scripts/governance/validate-*.sh is
#      referenced somewhere in the registry table.
# A rule or validator added without a registry row is exactly the kind of
# silent coverage gap this table exists to make visible — so an omission here
# is a FAIL, not a WARN.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
README=".claude/rules/README.md"
RULES_DIR=".claude/rules"
VALIDATORS_DIR="scripts/governance"
fail=0

[ -f "$README" ] || { echo "FAIL enforcement-registry: $README not found"; exit 1; }

REGISTRY_START=$(grep -n "^## Enforcement Registry" "$README" | head -1 | cut -d: -f1)
if [ -z "$REGISTRY_START" ]; then
  echo "FAIL enforcement-registry: no '## Enforcement Registry' section in $README"
  exit 1
fi
registry_text=$(tail -n +"$REGISTRY_START" "$README")

# 1. every rule file appears in the registry text
for f in "$RULES_DIR"/*.md; do
  base="$(basename "$f")"
  [ "$base" = "README.md" ] && continue
  if echo "$registry_text" | grep -qF "$base"; then
    echo "PASS enforcement-registry: $base has a registry row"
  else
    echo "FAIL enforcement-registry: $base has NO registry row — add one to $README"
    fail=1
  fi
done

# 2. every validator script appears in the registry text
for f in "$VALIDATORS_DIR"/validate-*.sh; do
  base="$(basename "$f")"
  # the registry table itself and validate-all.sh are orchestration, not gates
  case "$base" in
    validate-enforcement-registry.sh|validate-all.sh) continue ;;
  esac
  if echo "$registry_text" | grep -qF "$base"; then
    echo "PASS enforcement-registry: $base is referenced in the registry"
  else
    echo "FAIL enforcement-registry: $base exists but is NOT referenced in the registry — add a row"
    fail=1
  fi
done

[ $fail -eq 0 ] && echo "PASS enforcement-registry: table is in sync with rules + validators"
exit $fail
