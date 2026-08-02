#!/usr/bin/env bash
# validate-memory-sync.sh — memory staleness guard (governance apparatus,
# 2026-08-02). Complements validate-bridge-health.sh (which checks orphan
# context / link health) with two different checks:
#
#   1. Index completeness — every .agents/memory/*.md file is referenced from
#      MEMORY.md, and every .md link IN MEMORY.md resolves to a real file.
#   2. Stale-claim heuristic — a memory file that says "OPEN as of" / "Status:
#      OPEN" while naming a validate-*.sh script that CURRENTLY EXITS 0 is a
#      contradiction: the finding claims to be open but its own cited gate
#      says it's fixed. WARN (not FAIL) — a human still verifies the claim
#      is genuinely stale before editing it (that verification is what
#      /wrap-session's reconciliation pass does).
#
# This targets Class 2 in .agents/memory/bug-classes.md (evidence drift) —
# hit for real on 2026-08-02 when two memory files claimed OPEN status for
# findings the code had already fixed.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
DIR=".agents/memory"
INDEX="$DIR/MEMORY.md"
GOV="scripts/governance"
fail=0

[ -d "$DIR" ] || { echo "validate-memory-sync: no $DIR (skip)"; exit 0; }
[ -f "$INDEX" ] || { echo "FAIL memory-sync: $INDEX not found"; exit 1; }

mapfile -t files < <(find "$DIR" -maxdepth 1 -type f -name '*.md' ! -name 'MEMORY.md' | sort)

# ── 1a. every memory file is referenced from MEMORY.md ───────────────────────
index_text="$(cat "$INDEX")"
for f in "${files[@]}"; do
  base="$(basename "$f")"
  if echo "$index_text" | grep -qF "$base"; then
    echo "PASS memory-sync: $base is indexed in MEMORY.md"
  else
    echo "FAIL memory-sync: $base exists but MEMORY.md has no line for it"
    fail=1
  fi
done

# ── 1b. every .md link in MEMORY.md resolves to a real file ──────────────────
while IFS= read -r link; do
  [ -f "$DIR/$link" ] || {
    echo "FAIL memory-sync: MEMORY.md links to '$link' which does not exist in $DIR"
    fail=1
  }
done < <(grep -oE '\(([A-Za-z0-9._-]+\.md)\)' "$INDEX" | tr -d '()' | sort -u)

# ── 2. stale-claim heuristic ──────────────────────────────────────────────────
# PRAGMA: a file that discusses this exact status-line convention as prose
# (e.g. bug-classes.md's own Class 2 writeup) can suppress a single false
# match with an inline comment: <!-- memory-sync-ok: quoting the pattern -->
# on the same line. Every pragma needs a written justification, same
# discipline as the silent-failure-ok pragma elsewhere in this repo.
for f in "${files[@]}"; do
  base="$(basename "$f")"
  # "OPEN as of <date>" is this repo's actual status-line convention (see the
  # existing memory files). Deliberately narrower than a bare "Status: OPEN"
  # match, which false-positives on files that quote the pattern as an
  # EXAMPLE rather than asserting their own status.
  match_line=$(grep -inE 'open as of [0-9]' "$f" | grep -v 'memory-sync-ok' || true)
  [ -z "$match_line" ] && continue
  # find every validate-*.sh this file names
  while IFS= read -r script_name; do
    # never shell out to self — avoids recursion if a memory file names this
    # script (e.g. this file's own header comment)
    [ "$script_name" = "validate-memory-sync.sh" ] && continue
    script_path="$GOV/$script_name"
    [ -f "$script_path" ] || continue
    if bash "$script_path" >/dev/null 2>&1; then
      echo "WARN memory-sync: $base claims OPEN but its own cited gate ($script_name) currently PASSES — re-verify before trusting this file's status"
    fi
  done < <(grep -oE 'validate-[A-Za-z0-9_-]+\.sh' "$f" | sort -u)
done

[ $fail -eq 0 ] && echo "PASS memory-sync: index complete, no broken links"
exit $fail
