#!/usr/bin/env bash
# validate-secrets-hygiene.sh — enforce .claude/rules/secrets-hygiene.md
# The repo is PUBLIC. This gate is the last thing between a secret and the world.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
fail=0

# 1. .gitignore must cover .env
if [ -f .gitignore ] && grep -qE '^\.env$|^\.env\.\*|^\*\.env' .gitignore; then
  echo "PASS secrets: .gitignore covers .env"
else
  echo "FAIL secrets: .gitignore has NO .env rule — a local .env can be committed to a PUBLIC repo"
  fail=1
fi

# 2. no .env-pattern file tracked (except .env.example)
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  tracked=$(git ls-files | grep -E '(^|/)\.env($|\.)|\.env$' | grep -v '\.env\.example$' || true)
  if [ -n "$tracked" ]; then
    echo "FAIL secrets: env file(s) tracked by git:"; echo "$tracked"
    echo "  -> ROTATE the keys. Removing the commit does not unpublish them."
    fail=1
  else
    echo "PASS secrets: no .env tracked (only .env.example)"
  fi

  # 3. credential-shaped literals in tracked source
  #    (local docker-compose creds against db/localhost/minio are excluded —
  #     they are not secrets; a real host with credentials is)
  hits=$(git ls-files -- '*.py' '*.ts' '*.tsx' '*.js' '*.json' '*.yaml' '*.yml' '*.md' 2>/dev/null \
    | grep -v '\.env\.example$' \
    | xargs grep -InE "(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|postgres(ql)?://[^:@/\"' ]+:[^@\"' ]+@)" 2>/dev/null \
    | grep -viE "example|placeholder|your[-_]|dummy|fake|xxx|<.*>" \
    | grep -vE "@(db|localhost|127\\.0\\.0\\.1|postgres|minio|host\\.docker\\.internal):" || true)
  if [ -n "$hits" ]; then
    echo "FAIL secrets: credential-shaped literal in tracked source:"; echo "$hits"; fail=1
  else
    echo "PASS secrets: no credential-shaped literals in tracked source"
  fi

  # 4. documents committed outside fixtures — possible real contracts
  docs=$(git ls-files -- '*.docx' '*.pdf' 2>/dev/null | grep -viE "fixture|test|sample|template|docs/" || true)
  if [ -n "$docs" ]; then
    echo "WARN secrets: document file(s) tracked outside fixtures — confirm no personal data:"
    echo "$docs"
  else
    echo "PASS secrets: no stray document files tracked"
  fi
else
  echo "SKIP secrets: not a git checkout (tracked-file checks unavailable)"
fi

[ $fail -eq 0 ] && echo "PASS secrets-hygiene"
exit $fail
