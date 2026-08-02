---
name: wrap-session
description: Session-close reconciliation ritual for LANDY Creator — present errors/lessons found this session, get MV's permission, then commit the learnings to both the Claude corpus (rules/memory/bug-classes/advancements) and Notion (factual status + progress note on every touched Build Action Items row). Use on "/wrap-session", "wrap up", "close out this session", or when the Stop-hook reminder fires after money-path files were touched.
---

# /wrap-session — nothing gets left behind

MV's standing requirement: at the end of a coding job, present the
challenges/errors/bugs found and the lessons learned, then **ask permission**
before writing anything durable — and if new information is proven
beneficial, commit it, on both sides of this project's split truth: the
Claude corpus (`.claude/rules/`, `.agents/memory/`) *and* Notion (the
canonical Build Action Items to-do list). Neither side gets left behind.

This is not a rubber-stamp. Do the reflection honestly — a session with
nothing worth promoting should say so and stop, not manufacture a memory
entry to look thorough.

## Step 1 — Reflect

Enumerate, from what actually happened this session (not from memory of what
*should* have happened):

- **Money-path files touched** — cross-reference against the file lists in
  `silent-failure.md`, `unknown-state.md`, and the other rule FAIL conditions.
- **Errors / hiccups hit**, each with: what broke, the root cause, and the
  fix (applied or still needed). Include environment/toolchain hiccups, not
  just logic bugs — those are exactly what `bug-classes.md` Class 3/4 exist
  for.
- **New facts** learned about the codebase, product, or MV's constraints that
  aren't yet written down anywhere.
- **Decisions** MV made this session (design calls, tradeoffs, scope calls).
- **Notion rows** (LC-#) this session's work is about, and what changed for
  each — cite it to a commit, a validator result, or a test outcome. If you
  cannot cite a specific piece of evidence for a claim, it doesn't go in the
  write-back.

## Step 2 — Classify

Sort each reflection-step item into exactly one tier, per CLAUDE.md's
Auto-update protocol:

| Tier | Target | When |
|---|---|---|
| 1 | `.claude/rules/*.md` + a validator | The lesson must bind future sessions mechanically. |
| 2 | `.agents/memory/*.md` + `MEMORY.md` | A durable finding/decision that informs judgment but isn't a rule. |
| 3 | PR description only | Worth recording once, not worth a standing file. |
| 4 | `.agents/memory/claude-code-advancements.md` | An idea about Claude Code's OWN tooling/workflow, not a product finding. |
| — | `.agents/memory/bug-classes.md` | A *recurring failure shape* (not a one-off) — orthogonal to the tiers above; log it whether or not it's also promoted to a rule. |

A vague "went well" is not a reflection item. Only classify things concrete
enough that a future session could act on them.

## Step 3 — Present and ask permission

Use `AskUserQuestion` (or, for a short list, plain text with a clear yes/no)
to show MV the classified batch **before writing anything**. Batch by target
surface so MV can approve/reject/edit each group, not each line. Never write
a rule, memory file, or Notion update without this step completing first —
this is the gate the paired rule (`session-reconciliation.md`) makes binding.

## Step 4 — Commit the learnings (only after approval)

**A. Claude corpus:**
- Tier 1 → edit/create the rule file (What/Why + FAIL condition +
  WHERE-checked + Enforcement strength) and its validator; wire into
  `validate-all.sh`; add a row to the Enforcement Registry table in
  `.claude/rules/README.md`.
- Tier 2 → new/updated file in `.agents/memory/` + a line in `MEMORY.md`.
- Tier 4 → append to `claude-code-advancements.md` (Shipped / In progress /
  Queued, with a revisit trigger if deferred).
- Bug-class → append to `bug-classes.md` if the shape is new; cite the
  instance in an existing class if it recurs.
- Regenerate any registered `*-INDEX.md` whose source changed
  (`cd scripts && npx tsx ./src/index-headings.ts`), then verify with
  `--check`.

**B. Notion — mandatory whenever the session touched a Build Action Items
row, factual only:**
- Fetch each touched LC-#'s current page (`notion-fetch` or
  `notion-query-data-sources`) to confirm its present Status before writing —
  never overwrite blind.
- Update `Status` to the state the evidence actually supports (`In review`,
  `Done`, `Blocked`, etc.) — never advance a status the job didn't earn.
- Append a page-body note (`notion-update-page`, `insert_content` at the
  end) stating: what was done, what was verified (cite the validator/test/
  commit), and what remains open. **Never fabricate a "done" claim** — if a
  DB-integration test couldn't run locally and needs a Replit re-run, say
  that explicitly rather than presenting it as verified.
- This exists because Notion is the to-do source Claude Code reads *before*
  acting on any LC-# (CLAUDE.md Step 0) — a stale or invented Notion state
  corrupts the next session's starting assumptions, which is a worse failure
  than not updating Notion at all. When in doubt, under-claim.

## Step 5 — Verify

Run `bash scripts/governance/validate-all.sh` and report the result. If a new
rule/validator was added this session, confirm it fires correctly (a
deliberate before/after test, not just "should work") before declaring the
session closed.

## Output

A short closing report: what was reflected on, what MV approved vs. declined,
what was written where (Claude corpus files + Notion rows, each with a
link/path), and the final `validate-all.sh` result. If nothing rose to a
committable tier, say so plainly — "no durable learnings this session" is a
valid and honest output.
