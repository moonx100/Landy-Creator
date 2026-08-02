#!/usr/bin/env bash
# money-path-guard.sh — PreToolUse hard-stop for money-path commits
# (governance apparatus, 2026-08-02; the "hard-stop then retry" pattern).
#
# Wired as a PreToolUse hook on the Bash tool in .claude/settings.json. Claude
# Code sends the hook a JSON payload on stdin describing the tool call; this
# script:
#   1. Extracts tool_input.command. If it isn't a `git commit`, allow (exit 0)
#      immediately — this must be a near-zero-cost no-op for every other
#      Bash call, which is the overwhelming majority.
#   2. If it is a commit, lists staged files and checks them against the
#      money-path file list below (see comment for how that list was derived).
#   3. If none match, allow.
#   4. If any match, run the full governance suite. Exit 2 (BLOCK — stderr is
#      surfaced to Claude as the reason) if it fails; exit 0 (allow) if it
#      passes.
#
# FAIL-OPEN ON INTERNAL ERROR, BY DESIGN. Any unexpected error in THIS
# script's own logic (missing python, malformed stdin JSON, git failure)
# degrades to "allow" with a warning on stderr — never to "block". A hook bug
# blocking a legitimate commit with a cryptic reason is worse than the rare
# window where a bug lets one uncaught commit through; validate-all.sh at
# task close and /wrap-session's reconciliation pass remain the backstop.
# Only a CONFIRMED validator failure on a CONFIRMED money-path file set
# produces exit 2.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"

fail_open() {
  echo "money-path-guard: $1 — allowing (fail-open by design; see script header)" >&2
  exit 0
}

# Pick a python interpreter that ACTUALLY RUNS — on Windows, `python3` is
# often a PATH entry that resolves via `command -v` but is really a Microsoft
# Store install-stub that fails at invocation time ("Python was not found;
# run without arguments to install..."). Probe with --version, don't trust
# command -v alone.
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || fail_open "no working python interpreter found (python3/python both absent or stubbed)"

payload="$(cat)"
[ -n "$payload" ] || fail_open "empty stdin payload"

# Extract tool_input.command with Python's json module (no jq dependency
# assumed). Prints nothing (and this script fails open) if the field is
# absent or the payload isn't valid JSON — e.g. a non-Bash tool call.
command_str="$("$PY" -c '
import json, sys
try:
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
    print(cmd)
except Exception:
    pass
' <<< "$payload" 2>/dev/null)" || fail_open "failed to parse hook payload JSON"

# Fast path: anything that is not a git-commit invocation is out of scope.
echo "$command_str" | grep -qE '(^|[;&|]|\s)git\s+commit(\s|$)' || exit 0

staged="$(git diff --cached --name-only 2>/dev/null)" \
  || fail_open "git diff --cached failed (not a git repo? detached state?)"
[ -n "$staged" ] || exit 0   # nothing staged — let git's own empty-commit error handle it

# ── Money-path file list ──────────────────────────────────────────────────
# Derived from the FAIL conditions of silent-failure.md, unknown-state.md,
# extraction-coverage.md, tracked-changes-authenticity.md, and
# redact-before-inference.md, narrowed from those rules' full
# "artifacts/landy-api/" scope down to the SPECIFIC files with a documented
# incident history (materiality-default-gap.md, redaction-diff-path-gap.md,
# unknown-state-pattern.md) plus the directories those rules name explicitly
# (export/, routes/, migrations/versions/). The broader per-rule scope stays
# covered by self-audit (/review-gate, /export-gate) and validate-all.sh at
# close — this hook is deliberately narrow so it fires on real risk, not on
# every backend edit.
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

matched=""
while IFS= read -r pattern; do
  [ -z "$pattern" ] && continue
  hit="$(echo "$staged" | grep -E "$pattern" || true)"
  [ -n "$hit" ] && matched="$matched$hit"$'\n'
done <<< "$MONEY_PATH_PATTERNS"

[ -n "$matched" ] || exit 0   # staged files exist, none are money-path

echo "money-path-guard: staged money-path file(s) detected:" >&2
echo "$matched" >&2
echo "money-path-guard: running scripts/governance/validate-all.sh before allowing the commit..." >&2

if bash scripts/governance/validate-all.sh >/tmp/money-path-guard-output.$$ 2>&1; then
  echo "money-path-guard: validate-all.sh PASSED — commit allowed" >&2
  rm -f "/tmp/money-path-guard-output.$$"
  exit 0
else
  echo "money-path-guard: BLOCKED — validate-all.sh failed on staged money-path changes." >&2
  echo "Fix the failing gate(s) below, re-stage, and commit again:" >&2
  tail -60 "/tmp/money-path-guard-output.$$" >&2
  rm -f "/tmp/money-path-guard-output.$$"
  exit 2
fi
