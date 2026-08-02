# LANDY Creator — binding rules

<!-- gate-first-exempt: index file; declares no rule of its own -->

Twelve rule files. Every one is written **gate-first**: What/Why + **FAIL
condition** + **WHERE-checked** + **Enforcement strength**.
`scripts/governance/validate-gate-first.sh` mechanically fails any that isn't.

## Creator money-path (new — authored for this product)

| Rule | Guards |
|---|---|
| `legal-advice-framing.md` | Every user-facing string is information, not advice (UPL). |
| `redact-before-inference.md` | No un-redacted PII reaches an LLM (UU PDP). |
| `extraction-coverage.md` | Non-empty text is not proof of successful extraction. |
| `tracked-changes-authenticity.md` | Real OOXML `w:ins`/`w:del`, never simulated formatting. |
| `tenant-isolation.md` | Explicit `WHERE user_id` is the isolation layer; RLS is second. |
| `secrets-hygiene.md` | Nothing secret and no user data enters git. The repo is public. |
| `unknown-state.md` | Every classification/parse step has a representable, rendered "we don't know" state (LC-41). **Proposed 2026-08-02 — binds after MV sign-off on the LC-41 PR.** |

## Carried from landy-workspace (adapted to Creator paths)

| Rule | Adaptation |
|---|---|
| `silent-failure.md` | Re-pointed from ingest/scraping to extraction/LLM/analysis paths. |
| `status-integrity.md` | `statutes.status`; schema already compliant — this is a regression guard. |
| `provenance.md` | Corpus half at schema level; answer half applies to risk-flag citations. |
| `statutory-vs-doctrinal.md` | `statutes.tier_basis` + `citations.basis`. |

## Dormant

| Rule | Why |
|---|---|
| `source-access.md` | Creator does not scrape. Armed for the mini-corpus build. |

**Promotion boundary:** only files in this directory, `CLAUDE.md`, registered
hooks, and `.claude/skills/` bind. `.agents/memory/` is evidence.
