# LANDY Creator — Operating Manual (Claude Code)

Applies to the `Landy-Creator` monorepo only. LANDY Creator is a contract-review
and negotiation-coaching product for Indonesian content creators, influencers,
artists and freelancers. Creators upload brand/agency contracts; the app flags
legal risks, explains them in Bahasa Indonesia, and produces a redlined DOCX +
negotiation email draft. Invite-only beta (10–20 users), launched via the
**YesMadameLawyer** persona.

**Every user-facing surface must carry: "informasi hukum, bukan nasihat hukum."**

This project is **independent**. Do not import rules, data, canon, or conventions
from `landy-workspace` (the fintech RegMap pilot) or any other workspace unless
MV explicitly asks for a read-only comparison. Creator is a *sibling* product to
RegMap and Legal Discovery, not a fork of them.

This file is the canonical operating manual. There is no separate
`LANDY_PROJECT_INSTRUCTIONS.md` — it was folded in here deliberately (one router,
not two). `replit.md` remains authoritative for **Replit run/deploy specifics
only** (workflows, ports, env wiring); it does not carry governance.

---

## Step 0 — Load the router

Before any Creator work, read, in order:

1. This file.
2. `.claude/rules/` — the binding rule surfaces (start with `README.md`, the index).
3. `.agents/memory/MEMORY.md` — the second brain index; follow links relevant to the task.
4. `replit.md` — only if the task touches running/deploying on Replit.

Then `git pull` before writing anything (see *Two write paths* below).

## Rule Promotion Boundary

Only `CLAUDE.md`, `.claude/rules/*.md`, registered hooks, `.claude/skills/*`, and
`.claude/commands/*` **bind**.

`.agents/memory/*`, `docs/*`, `replit.md`, `attached_assets/*`, reports, and
handoffs are **evidence**, not law. Evidence informs judgment; it does not
constrain a future session. If a finding must constrain future sessions, it gets
promoted to a rule file with a validator — nothing binds by being written down
somewhere.

## Two conventions, deliberately bridged

Creator carries two agent-facing directories. This is intentional; do not
consolidate them.

| Directory | Role | Rule |
|---|---|---|
| `.claude/` | **Law** — rules, gate skills, hooks. Natively read by Claude Code. | Author here. |
| `.agents/memory/` | **Evidence** — the second brain (findings, decisions, constraints). | Append here; never delete, mark superseded inline. |
| `.agents/skills/` | External design/frontend skills, pinned by `skills-lock.json` with content hashes. | **Do not edit, move, or rename.** Editing breaks the lockfile hash and the next `skills add` sync will revert it. |

`.agents/skills/` and `.claude/skills/` serve different ecosystems and different
purposes: the former is a vendored design toolkit, the latter is this project's
own compliance gates. They coexist.

## Handoffs

Session/task handoff reports (e.g. "what was done" summaries meant to brief a
fresh chat or the next session) go in `docs/handoff/`. This directory is
**gitignored** — handoffs are local working notes, not published evidence, and
never need to survive a `git push`. Don't put them in `.agents/memory/`
(that's durable evidence, appended-not-deleted) or commit them anywhere else in
the tree.

## Money-path — the legal-correctness path

Creator's catastrophic-failure surface is **a wrong or missed legal claim shown
to a creator who then signs**, not a code crash. A missed material risk in a
brand contract is Creator's equivalent of a wrong trade: silent, plausible-
looking, and discovered only when it has already cost the user.

Highest ceremony — independent verification before it ships — attaches to:

- any risk flag, severity, or `negotiation_ask` shown to a user;
- any materiality classification on the version-diff path;
- any exported artifact (redlined DOCX, negotiation email) that leaves the platform;
- any string that could be read as telling a user what to do legally.

The asymmetry that governs every default in this codebase: **a false "no risk"
is far worse than a false "possible risk."** When a classification, extraction,
or LLM call fails, degrade toward *flagging for human review* — never toward
silence, and never toward a reassuring default.

## Hard gates

- **AI output is information, not legal advice.** Every user-facing surface
  carries the disclaimer. Never assert a legal conclusion or instruct a user to
  sign/refuse. → `.claude/rules/legal-advice-framing.md`
- **Redact PII before every inference call.** No `chat_complete()` receives
  un-redacted document text. → `.claude/rules/redact-before-inference.md`
- **No silent near-empty extraction.** Non-empty ≠ successful. A 51-character
  extraction from a 20-page contract is a failure, not a short document.
  → `.claude/rules/extraction-coverage.md`
- **Real OOXML tracked changes only.** `w:ins` / `w:del` markup — never
  blue-bold/red-strikethrough formatting posing as a redline. Brand-side counsel
  must be able to accept/reject. → `.claude/rules/tracked-changes-authenticity.md`
- **Tenant isolation is the explicit `WHERE user_id` predicate.** RLS is
  defense-in-depth only and is a **no-op** under the current superuser
  `DATABASE_URL`. → `.claude/rules/tenant-isolation.md`
- **Silent failure is a bug.** No `except: pass`; no substantive default
  (`"immaterial"`, `ok=True`) written on a failure path without a surfaced flag.
  → `.claude/rules/silent-failure.md`
- **`statutes.status` is operator-assigned only** — never scraped, inferred, or
  auto-set. → `.claude/rules/status-integrity.md`
- **Statutory vs. doctrinal, always labeled** — `citations.basis` and
  `statutes.tier_basis` never blend codified statute with inference.
  → `.claude/rules/statutory-vs-doctrinal.md`
- **Provenance on every corpus record** — `source_url`, `retrieved_date`,
  `sha256`. → `.claude/rules/provenance.md`
- **No secret-value reads, and no secret ever reaches git.** Reference `.env`
  variable names only; never print or echo a value. The repo is **public** —
  treat every commit as published. → `.claude/rules/secrets-hygiene.md`
- **Creator does not scrape.** → `.claude/rules/source-access.md` (dormant until
  the mini-corpus build; do not read it as evidence a scraper exists).

## Task-type quick router

| Signal | Load additionally |
|---|---|
| extraction / parser / upload | `extraction-coverage`, `silent-failure`; run `/review-gate` |
| analysis / risk flags / taxonomy / LLM prompt | `redact-before-inference`, `legal-advice-framing`, `silent-failure`; run `/review-gate` |
| diff / materiality | `redact-before-inference`, `silent-failure` (the `"immaterial"` default is a known live gap); run `/review-gate` |
| export / DOCX / email draft | `tracked-changes-authenticity`, `legal-advice-framing`; run `/export-gate` |
| routes / DB / migrations | `tenant-isolation`; read `.agents/memory/rls-superuser-constraint.md` first |
| statute corpus / citations | `provenance`, `status-integrity`, `statutory-vs-doctrinal` |
| frontend / UI | `.agents/skills/` design skills; `legal-advice-framing` for copy |

## Verify before you close

```bash
bash scripts/governance/validate-all.sh
```

Run at task close and in CI. Some gates **fail on a clean checkout today** —
those are real, logged findings, not broken validators. See
`.agents/memory/MEMORY.md`. Do not "fix" a validator to make it pass; fix the
code, or record why the gap stands.

## Git workflow — commit to `main`, pull first

Creator is written to from both the Replit web integration and Claude Code
Desktop. The hazard that creates is **divergence**, not bad code: work sitting
uncommitted on one path while the other pushes. So the discipline is frequency,
not ceremony.

**Default — commit straight to `main`:**

1. `git pull` **before** starting any work. Always. This is the rule that matters.
2. Do the work.
3. `git add -A && git commit && git push` at the end of the task. Do not leave a
   task's changes uncommitted overnight.
4. Small, frequent commits beat large ones. A commit per task, not per session.

MV is a solo operator. A pull request MV opens, reviews, and merges alone is
theatre — it adds steps without adding a reviewer. Do not create branches by
default, and do not ask MV to review a PR that only MV could have written.

**Branch + PR only for these — where `git revert` does not undo the damage:**

- **Alembic migrations.** A migration pushed to `main` and then run by Replit
  against the live database has already changed the data. Reverting the commit
  does not reverse it. Branch, and state the rollback plan in the PR.
- **Anything touching the money-path fix list** in `.agents/memory/` —
  redaction, materiality defaults, extraction coverage. These change what a user
  is told about their contract; they deserve a second look before they land.
- **Deleting or rewriting history.** Never force-push `main`. Never rewrite a
  commit another write path may already hold.

Everything else — features, fixes, refactors, governance edits, documentation —
goes straight to `main`.

**Never commit:** `.env`, credentials, real contracts, or anything containing a
user's or counterparty's personal data. See `.claude/rules/secrets-hygiene.md`.
If a secret has already been pushed, rotating the key is the fix; deleting the
commit is not.

## Auto-update protocol

After substantive work, offer durable learnings, classified:

- **Tier 1** → a `.claude/rules/` edit (binding; needs a validator).
- **Tier 2** → a new note in `.agents/memory/` + a line in `MEMORY.md`.
- **Tier 3** → mention in the PR description only.

Write only after MV approval. MV is a former financial-services regulator and
practising Indonesian advocate — that domain authority is a core project asset.
Invite MV's verification of legal reasoning; never assert legal conclusions
autonomously, and never resolve an open legal question by picking the plausible
answer.
