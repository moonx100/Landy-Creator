#!/usr/bin/env bash
# validate-legal-advice-framing.sh — enforce .claude/rules/legal-advice-framing.md
# (1) disclaimer reachable on user-facing analysis surfaces
# (2) every LLM system prompt carries an information-not-advice instruction
# (3) FAIL on advisory imperatives aimed at the user
# (4) WARN on outcome-assertion vocabulary in prompts — MV's register judgment
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
API="artifacts/landy-api/landy"
fail=0
DISC='nasihat hukum|legal advice|bukan pengganti konsultasi'

# 1. disclaimer presence per user-facing app
for app in artifacts/landy-web artifacts/landy-mobile; do
  [ -d "$app" ] || continue
  if grep -rIqE "$DISC" "$app" --include="*.tsx" --include="*.ts" 2>/dev/null; then
    echo "PASS advice-framing: disclaimer present in $app"
  else
    echo "FAIL advice-framing: no disclaimer string anywhere in $app"; fail=1
  fi
done

# 2. export generators must carry a disclaimer
if [ -d "$API/export" ]; then
  for f in "$API"/export/*.py; do
    case "$(basename "$f")" in __init__.py) continue;; esac
    if grep -qIE "$DISC" "$f"; then echo "PASS advice-framing: disclaimer in $(basename "$f")"
    else echo "FAIL advice-framing: export generator without disclaimer: $f"; fail=1; fi
  done
fi

# 3. every system prompt must instruct information-not-advice
mapfile -t pf < <(grep -rIln "_SYSTEM_PROMPT\|SYSTEM_PROMPT =" "$API" --include="*.py" 2>/dev/null | sort -u)
for f in "${pf[@]}"; do
  if grep -qIE "$DISC|informasi hukum" "$f"; then
    echo "PASS advice-framing: system prompt in $(basename "$f") carries information-not-advice framing"
  else
    echo "FAIL advice-framing: system prompt without information-not-advice instruction: $f"; fail=1
  fi
done

# 4. HARD FAIL — advisory imperatives directed at the user
adv=$(grep -rInE "Anda[[:space:]]+(harus|wajib|sebaiknya)[[:space:]]+(menandatangani|tanda ?tangan|menolak|membatalkan|memutuskan)|you[[:space:]]+(should|must)[[:space:]]+(sign|refuse|terminate|reject)" \
      "$API" --include="*.py" 2>/dev/null || true)
if [ -n "$adv" ]; then
  echo "FAIL advice-framing: advisory imperative directed at the user:"; echo "$adv"; fail=1
else
  echo "PASS advice-framing: no advisory imperative directed at the user"
fi

# 5. WARN — outcome-assertion vocabulary. Often legally correct in a prompt
#    (e.g. moral rights are inalienable under UU 28/2014 Pasal 5) but it
#    propagates into user-facing text as a determination. MV's register call.
out=$(grep -rInE "batal demi hukum|tidak sah secara hukum|null and void" "$API" --include="*.py" 2>/dev/null || true)
if [ -n "$out" ]; then
  echo "WARN advice-framing: outcome-assertion vocabulary — verify it renders as information, not determination:"
  echo "$out"
fi

# 6. prompts must not invite invented statute references while the corpus is empty
inv=$(grep -rInE "(sebutkan|cantumkan|cite|include)[^\"']{0,40}(pasal|ayat)[[:space:]]+(yang|nomor|terkait|relevan)" \
      "$API" --include="*.py" 2>/dev/null || true)
if [ -n "$inv" ]; then
  echo "FAIL advice-framing/provenance: prompt invites a statute citation with an empty corpus:"
  echo "$inv"; fail=1
else
  echo "PASS advice-framing: no citation-invention instruction in prompts"
fi

[ $fail -eq 0 ] && echo "PASS legal-advice-framing"
exit $fail
