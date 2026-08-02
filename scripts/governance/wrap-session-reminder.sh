#!/usr/bin/env bash
# wrap-session-reminder.sh — advisory Stop hook (governance apparatus,
# 2026-08-02). Fires after every Claude Code turn ends. ADVISORY ONLY: always
# exits 0, never blocks. Its only job is to print a reminder to stderr when
# there is uncommitted or very-recently-committed work touching a money-path
# file pattern, so /wrap-session isn't forgotten by omission.
#
# Deliberately cheap and silent in the common case — most turns touch
# nothing money-path-shaped and this should print nothing.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT" 2>/dev/null || exit 0

# Never let this reminder itself fail the turn — any error here is silent.
trap 'exit 0' ERR

MONEY_PATH_PATTERNS='
artifacts/landy-api/landy/diff/materiality\.py
artifacts/landy-api/landy/diff/pipeline\.py
artifacts/landy-api/landy/analysis/pipeline\.py
artifacts/landy-api/landy/tracked_changes\.py
artifacts/landy-api/landy/doc_comments\.py
artifacts/landy-api/landy/extraction\.py
artifacts/landy-api/landy/export/
artifacts/landy-api/landy/routes/
artifacts/landy-api/migrations/versions/
'

# Uncommitted changes (staged + unstaged) plus the tip commit, so the
# reminder still fires right after /wrap-session's own commit step, not just
# before it.
changed="$( { git status --porcelain 2>/dev/null | awk '{print $2}'; \
              git show --name-only --format= HEAD 2>/dev/null; } | sort -u)"
[ -n "$changed" ] || exit 0

hit=""
while IFS= read -r pattern; do
  [ -z "$pattern" ] && continue
  m="$(echo "$changed" | grep -E "$pattern" || true)"
  [ -n "$m" ] && hit="yes"
done <<< "$MONEY_PATH_PATTERNS"

[ -n "$hit" ] && echo "[LANDY Creator] Money-path files changed this session — run /wrap-session before closing out (reflect, classify, get MV's permission, commit learnings to both the Claude corpus and Notion)." >&2

exit 0
