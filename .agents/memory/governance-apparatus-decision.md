---
name: Governance apparatus decision — F4TALITY-inspired, right-sized for Creator
description: Why LANDY Creator adopted six F4TALITY-inspired governance mechanisms on 2026-08-02, and MV's two amendments to the original plan.
---

# The governance apparatus

## The decision

On 2026-08-02, immediately after the LC-41 unknown-state PR (#5) merged, MV
asked for a structural comparison against the F4TALITY trading project's
`.claude/` ruleset and directed adopting the full range (F4TALITY's own Tier
1–3 internal terminology) — not cargo-culted wholesale, but adapted to a
solo-operator, 10–20-user legaltech beta. Branch `feat/governance-apparatus`.

**Why now:** LANDY's money-path failure is *silent and deferred* (a wrong "no
risk" surfaces only when a creator signs, weeks later), unlike F4TALITY's
*loud and immediate* failures (a bad trade loses money now). That asymmetry
means mechanical gates and a forced reconciliation loop return more value
here than in the system they were copied from — this session's own governance
build proved the point twice (see [[bug-classes.md]] Classes 2, 4, 5, all
caught by tooling built in this same session, on files this same session had
just touched).

## The six pieces

1. **Bug-class registry** (`bug-classes.md`) — catalogs recurring *failure
   shapes*, not one-off bugs.
2. **Internal-advancements queue** (`claude-code-advancements.md`) — a
   dedicated home for Claude Code's own tooling/workflow ideas, separate from
   bug-classes.
3. **Enforcement Registry** — a single table in `.claude/rules/README.md`
   mapping trigger → rule → validator → mechanical/self-audit, plus a
   drift-guard validator.
4. **Memory staleness guard** (`validate-memory-sync.sh`) — catches a memory
   file claiming "OPEN" while its own cited gate now passes.
5. **INDEX auto-sync** (`scripts/src/index-headings.ts`) — deterministic
   heading-map generation for context-dense files, registration by judgment
   call rather than a hard line-count gate.
6. **Money-path hard-stop** (`money-path-guard.sh`, PreToolUse) + the
   **session-close reconciliation ritual** (`/wrap-session`,
   `session-reconciliation.md`) — the centerpiece MV asked for directly.

## MV's two amendments to the draft plan

**1. Notion write-back is mandatory in `/wrap-session`, not optional.** The
draft plan covered only the Claude-corpus half of "nothing gets left behind."
MV's correction: Notion is the canonical to-do source Claude Code reads
*before* acting on any Build Action Items row (`CLAUDE.md` Step 0) — so the
ritual must also update Status and append a factual, cited progress note to
every touched LC-# row, never fabricating a "done." A drifted or invented
Notion state is a worse failure than not writing back at all, because it
corrupts the next session's starting assumptions rather than merely leaving
them incomplete.

**2. Bug-classes and feature ideas are different kinds of ledger.** The
draft plan proposed deferring Tier-3-heavy F4TALITY items (named subagents,
delegation tiering, a full `/post-session` DB-audit, INDEX for short rule
files) into `bug-classes.md`. MV's correction: a deferred *feature* is not a
*bug* — they belong in the dedicated `claude-code-advancements.md` queue
instead, each with its own revisit trigger so the deferral is a decision, not
an omission.

## Scope guardrails (why this isn't the full F4TALITY apparatus)

Deferred, not rejected — filed in `claude-code-advancements.md` under
Queued/deferred with revisit triggers: named subagents with model floors,
delegation tiering, a full `/post-session` DB-audit workflow, INDEX for the
`.claude/rules/*.md` files themselves (none currently exceeds ~1 screen).
Each is F4TALITY-scale ceremony that costs more than it returns for a solo
operator today; the triggers say what would change that.

## Consequence

`validate-all.sh` grew from 14 to 17 gates in this session. First full run
after wiring: ALL PASS. First live run of the new memory-staleness guard
caught three real drift instances in files this branch had itself edited
minutes earlier (see [[bug-classes.md]] Class 2) — evidence the apparatus
targets a real, not hypothetical, failure mode.

Decided and built 2 Aug 2026. Related: `CLAUDE.md` (Auto-update protocol),
[[bug-classes.md]], [[claude-code-advancements.md]], `.claude/rules/session-reconciliation.md`,
`.claude/skills/wrap-session/SKILL.md`.
