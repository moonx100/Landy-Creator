# Refactor map — `landy-workspace` → `Landy-Creator`

Every file in the incoming `landy-workspace` copy, tagged **keep / adapt / drop**,
with its Creator target. This is the audit trail for the transplant.

**Totals:** 11 rules · 14 validators · 2 gate skills · 4 memory notes · 1 `.gitignore` block.

## Method note

The Creator repo was cloned and read directly rather than taken from the handoff's
§2 description. Three corrections came out of that (§ *Corrections logged* below).
Every validator in this package was executed against the real repo before
shipping — see `INSTALL.md` § *Expected first run*.

---

## Governance root

| landy-workspace | Disposition | Creator target | Note |
|---|---|---|---|
| `CLAUDE.md` | **adapt** | `CLAUDE.md` | Rewritten for Creator. Money-path redefined from *legal-authority correctness* to *a wrong or missed legal claim shown to a creator who then signs*. Router Step 0 re-pointed to `.agents/memory/`. Adds *Git workflow* (commit-to-`main` default; branch+PR reserved for Alembic migrations and money-path fixes) and the `.claude`/`.agents` bridge table. |
| `LANDY_PROJECT_INSTRUCTIONS.md` | **drop** (folded) | — | Resolves handoff §7.4. In landy-workspace it duplicates CLAUDE.md's money-path section verbatim and re-lists the same five constraints. Creator already carries `replit.md`; a third manual guarantees drift. One router. |
| `README.md` | **drop** | — | Creator has `replit.md` + a GitHub README. Nothing to add. |
| `.claude/settings.json` | **adapt** | `.claude/settings.json` | Same advisory-hook pattern; reminder text rewritten to Creator's gates. |
| `.semgrep/guardian.yml` | **drop** | — | **The file is empty (0 bytes) in the provided copy.** Carrying it would imply a static-analysis layer that does not exist. If semgrep is wanted later, author it deliberately. |
| `.env.example` | **drop** | — | Creator already has its own, matched to its actual env surface. |
| — | **new** | `gitignore-append.txt` → appended to `.gitignore` | Not from landy-workspace. Creator's `.gitignore` is Nx boilerplate with no `.env` rule, on a public repo. Append-only — the existing rules are legitimate. |
| `.remember/` | **drop** | — | Runtime logs from the `remember` Claude Code plugin (v0.8.3), `.gitignore`d with `*`. Machine output, not governance. Not mentioned in the handoff; worth knowing it exists so it isn't mistaken for a second brain. |

## Rules — `.claude/rules/`

| landy-workspace | Disposition | Creator target | Note |
|---|---|---|---|
| `status-integrity.md` | **adapt** | same name | Re-pointed to `statutes.status` under `artifacts/landy-api`. Schema is **already compliant** — this becomes a regression guard, not a fix. |
| `silent-failure.md` | **adapt** | same name | Substantially rewritten. Original targets WAF-interstitial false-empties; Creator has no scraper. Re-aimed at extraction/LLM/analysis, and extended with the **reassuring-default** clause, which is Creator's actual failure mode. |
| `provenance.md` | **adapt** | same name | Corpus half retained at schema level (corpus is empty by design in v1). Answer half re-aimed from RAG answers to risk-flag citations, with the *empty slot beats invented Pasal* rule made explicit. |
| `statutory-vs-doctrinal.md` | **adapt** | same name | Re-pointed from `hierarchy/ruleset.json` (absent) to `statutes.tier_basis` + `citations.basis`. |
| `source-access.md` | **adapt → dormant** | same name | Kept and clearly banner-marked DORMANT. Creator does not scrape. Armed for the mini-corpus build. |
| — | **new** | `legal-advice-framing.md` | Creator money-path. UPL + reliance. Governs the disclaimer *and* the register of generated text. |
| — | **new** | `redact-before-inference.md` | Creator money-path. UU PDP. Binds every `chat_complete()` call site. |
| — | **new** | `extraction-coverage.md` | Creator money-path. Non-empty ≠ extracted. |
| — | **new** | `tracked-changes-authenticity.md` | Creator money-path. Real OOXML `w:ins`/`w:del`. Regression guard — currently compliant. |
| — | **new** | `tenant-isolation.md` | From the RLS finding. Explicit `WHERE user_id` is primary; RLS is inert under the superuser role. |
| — | **new** | `secrets-hygiene.md` | Nothing secret and no user data enters git. Authored after discovering the repo is public and its `.gitignore` has no `.env` rule. Has no landy-workspace ancestor — that workspace is pre-git, so the question never arose. |
| — | **new** | `README.md` | Rule index. Carries the `gate-first-exempt` marker. |

## Validators — `scripts/governance/`

Placed under `scripts/governance/` per handoff §5, so the existing TS `scripts/`
package (`package.json`, `post-merge.sh`, `src/`, `tsconfig.json`) is untouched.
All paths resolve via `$(dirname $0)/../..`, so they work from any cwd.

| landy-workspace | Disposition | Creator target | Note |
|---|---|---|---|
| `validate-gate-first.sh` | **keep** (verbatim) | same name | Domain-blind rule-shape checker. Only the default rules dir resolution changed for the deeper path. |
| `compliance-eval.sh` | **keep** (verbatim) | same name | Domain-blind rubric engine. Reused by both new skills. |
| `validate-bridge-health.sh` | **adapt** | same name | Default corpus dir re-pointed `docs/second-brain` → `.agents/memory`. Inbound match tightened to `grep -F` on basename/wikilink — the original's unquoted `$stem` regex produced spurious matches on short stems. |
| `validate-all.sh` | **adapt** | same name | Re-ordered and re-populated: shape → money-path → carried → dormant. Carries an explicit note that failures on a clean checkout are real findings. |
| `validate-silent-failure.sh` | **adapt** | same name | Re-pointed `ingest rag` → `artifacts/landy-api`. Challenge-detection check **dropped** (no scraper). Added: reassuring-default detection, `needs_review` vocabulary check, and a `# silent-failure-ok:` pragma for legitimate raising fallback chains. |
| `validate-status-integrity.sh` | **adapt** | same name | Re-pointed to `artifacts/landy-api`; allowlist retained; `CHECK (status IN ...)` excluded from the grep so schema constraints don't self-trip. |
| `validate-provenance-schema.sh` | **adapt** | same name | Re-pointed `ingest/schema.sql` → `artifacts/landy-api/migrations/versions`. Extended to assert `tier_basis`, `citations.basis`, and the status `CHECK`. |
| `validate-hierarchy.sh` | **adapt** | same name | The `ruleset.json` half **dropped** (no such file in Creator). Retained: hardcoded `tier_rank` literal grep. Added: uncodified POJK/SEOJK ranking assertion grep. |
| `validate-source-access.sh` | **adapt → dormant** | same name | Denylist grep re-pointed `ingest rag graph` → `artifacts`. |
| `source-denylist.txt` | **keep** | same name | BPK. |
| `status-integrity-allowlist.txt` | **keep** | same name | Empty; allowlist additions need MV sign-off. |
| — | **new** | `validate-redaction-before-inference.sh` | Enumerates every `chat_complete()` call site. |
| — | **new** | `validate-extraction-coverage.sh` | Threshold constant + ratio check + bare-`strip()` anti-pattern. |
| — | **new** | `validate-tracked-changes.sh` | OOXML markup presence + simulated-redline anti-pattern. |
| — | **new** | `validate-legal-advice-framing.sh` | Disclaimer sweep, system-prompt framing, advisory-imperative FAIL, outcome-assertion WARN. |
| — | **new** | `validate-tenant-isolation.sh` | Route-level `user_id` predicate scan + RLS-as-primary assertion grep. |
| — | **new** | `validate-secrets-hygiene.sh` | `.gitignore` `.env` rule + tracked-env-file check + credential-literal grep + stray-document warning. Local docker-compose creds (`@db`, `@localhost`, `@minio`) excluded — not secrets. |
| — | **new** | `redaction-exempt.txt` | Empty. Exemptions need MV sign-off. |

## Skills

| landy-workspace | Disposition | Creator target | Note |
|---|---|---|---|
| `skills/ingest-check/` | **drop; re-author on the pattern** | `.claude/skills/review-gate/` | Resolves handoff §7.3. Creator has no acquisition path, so nothing was copied — only the *shape* (mechanical rubric + self-audit + escalate-to-MV + report). `/review-gate` covers upload → rendered risk flag. |
| `skills/hierarchy-audit/` | **drop; re-author on the pattern** | `.claude/skills/export-gate/` | Creator has no tier ruleset to audit. The equivalent RED-tier surface is the outbound artifact. `/export-gate` covers the redlined DOCX and negotiation email. |
| `skills/ingest-check/rubric.txt` | **adapt** | `review-gate/rubric.txt` | Same rubric grammar; checks re-authored against `extraction.py`. |
| — | **new** | `export-gate/rubric.txt` | Checks against `docx_export.py`. |

Location changed from top-level `skills/` to **`.claude/skills/`** — Claude Code
loads that path natively, and it avoids any appearance of collision with the
existing lockfile-managed `.agents/skills/`.

## Second brain

| landy-workspace | Disposition | Creator target | Note |
|---|---|---|---|
| `docs/second-brain/glossary.md` | **drop** | — | Terms are Indonesian contract-law terms already in the taxonomy and prompts, not a house vocabulary needing definition. Re-add only if real ambiguity appears. |
| `docs/second-brain/findings.md` | **adapt → split** | `.agents/memory/*.md` | The four-table schema is replaced by Creator's existing one-note-per-finding convention, which is the better design. Three real findings written up as standalone notes. |
| `docs/second-brain/decisions.md` | **adapt → split** | `.agents/memory/governance-convention-decision.md` | Same. |
| `docs/second-brain/interaction-learnings.md` | **drop for now** | — | Seed rows only in the provided copy; nothing earned. Re-introduce as a note when a real AI-wrong-claim → correction lesson lands. |
| `docs/second-brain/dossiers/` | **drop** | — | Per-regulation dossiers belong to RegMap. Revisit at the mini-corpus build. |

## Pipeline and domain code — all dropped

`ingest/` (`regmap_ingest.py`, `parse_pasal.py`, `url_discovery.py`,
`operator_status.py`, `schema.sql`), `rag/`, `graph/build_graph.py`,
`hierarchy/ruleset.json`, `hierarchy/concepts.json`, `data/`, `reports/`,
`handoffs/`, `crew/README.md`.

Per handoff §4, none of this belongs in Creator. Note in particular that
`hierarchy/ruleset.json` is the **input** to two carried rules — dropping it is
why `validate-hierarchy.sh` lost half its checks and why
`statutory-vs-doctrinal.md` was re-pointed at the database schema instead.

---

## Corrections logged against the incoming handoff

Recorded so they don't propagate into the next thread.

1. **The monorepo has five artifacts, not three.** §2 lists `landy-api`,
   `landy-web`, `api-server`. The repo also contains **`artifacts/landy-mobile/`**
   (a full Expo/React Native app with its own `server/`, `app/review`,
   `app/diff/[docId]`) and **`artifacts/mockup-sandbox/`**.

   *Amended after MV's clarification:* the omission was deliberate — mobile is
   **parked**, with focus on the web app. So this is a scope note, not a handoff
   error. It is recorded because it still bears on governance: `landy-mobile`
   remains a real user-facing surface, it currently carries the disclaimer on
   `login.tsx` only, and `validate-legal-advice-framing.sh` sweeps it. Left in
   scope on purpose — a parked app costs nothing to gate and is already armed
   when it unparks. The failure mode it guards against is that one string being
   stripped from `login.tsx` while nobody is watching mobile.

2. **The citation field is `citations.basis`, not `citation_basis`.** §4 names it
   `citation_basis`. A validator grepping the handoff's name would have passed
   vacuously against a column that does not exist.

3. **`.semgrep/guardian.yml` is empty.** §1 lists it among the scaffold's assets.
   It is a 0-byte file. Dropped rather than carried as decoration.

4. **`.remember/` is undocumented.** §1's inventory omits it. It is plugin runtime
   logging, fully `.gitignore`d — harmless, but it means landy-workspace actually
   ran *two* memory mechanisms, which matters when reasoning about what
   "the second brain" refers to.

5. **§4's live-bug list is accurate and now has line numbers.** Extraction
   `ok=True` on near-empty: `extraction.py` lines 85, 118, 148, 192. Materiality
   defaulting to `immaterial`: `materiality.py` lines 104, 109, 211. Both are
   logged as memory notes and both fail their gates.

6. **§4 understated the redaction problem.** It lists *"redact PII before
   inference"* as a rule to author. It is also a **live defect**:
   `diff/materiality.py` already sends non-redacted clause text to the model. This
   was found by executing the new validator against the repo, not by reading the
   handoff.

7. **Neither document addresses secrets hygiene, and the repo is public.**
   Cloning `moonx100/Landy-Creator` needs no credentials. Its `.gitignore` is
   generic Nx/Angular boilerplate with **no `.env` rule of any kind**, while
   `.env.example` names `LLM_API_KEY`, `S3_SECRET_KEY`, `SESSION_SECRET`,
   `ADMIN_SECRET`, and `DATABASE_URL`. Nothing is leaked today — only
   `.env.example` is tracked — but the exposure is one `git add -A` away, and the
   commit-to-`main` default adopted in `CLAUDE.md` makes that path more likely,
   not less. landy-workspace offers no precedent here: it is pre-git, so the
   question could not have arisen. Addressed by `secrets-hygiene.md`,
   `validate-secrets-hygiene.sh`, and `gitignore-append.txt`.

   Mitigating factor found in the same pass: `storage.py` sets
   `_LOCAL_ROOT = ~/.landy-dev-storage`, outside the working tree, so uploaded
   contracts do not land in the repo. That placement is a deliberate safety
   property and should be treated as load-bearing.

8. **§4's "real OOXML tracked changes" is already implemented correctly.**
   `docx_export.py` builds genuine `w:ins`/`w:del`/`w:delText` with `w:author` and
   `w:date`, and its docstring already forbids the simulated approach. The rule is
   worth keeping as a regression guard, but it is not outstanding work.
