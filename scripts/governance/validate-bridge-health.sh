#!/usr/bin/env bash
# validate-bridge-health.sh — domain-blind "no orphan context" checker. CARRIED.
# Re-pointed: the Creator second brain is .agents/memory (not docs/second-brain).
# STRICT ORPHAN (no inbound AND no outbound) -> FAIL. ZERO-INBOUND -> WARN.
# Usage: validate-bridge-health.sh [CORPUS_DIR]   (default: .agents/memory)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
DIR="${1:-.agents/memory}"
[ -d "$DIR" ] || { echo "validate-bridge-health: no dir $DIR (skip)"; exit 0; }
mapfile -t files < <(find "$DIR" -type f -name '*.md' | sort)
[ ${#files[@]} -eq 0 ] && { echo "validate-bridge-health: no .md files (skip)"; exit 0; }
fail=0
for f in "${files[@]}"; do
  base="$(basename "$f")"; stem="${base%.md}"
  outbound=0
  grep -qE '\[\[[^]]+\]\]|\]\([^)]*\.md|[A-Za-z0-9_-]+\.md' "$f" && outbound=1
  inbound=0
  for g in "${files[@]}"; do
    [ "$g" = "$f" ] && continue
    if grep -qF "$base" "$g" || grep -qF "[[$stem]]" "$g"; then inbound=1; break; fi
  done
  if [ $outbound -eq 0 ] && [ $inbound -eq 0 ]; then
    echo "FAIL (strict orphan): $f"; fail=1
  elif [ $inbound -eq 0 ]; then echo "WARN (zero-inbound): $f"
  else echo "PASS: $f"; fi
done
exit $fail
