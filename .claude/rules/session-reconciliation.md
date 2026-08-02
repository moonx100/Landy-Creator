# Rule: A money-path session does not close without a reconciliation pass

## What the rule requires

Any session that touches a money-path file (the file lists in
`silent-failure.md`'s and `unknown-state.md`'s FAIL conditions, or any Notion
Build Action Items row) runs the `/wrap-session` reconciliation ritual before
the session is treated as closed: reflect on errors/lessons found, classify
them per CLAUDE.md's Auto-update protocol, get MV's explicit permission, then
write the approved learnings to **both** the Claude corpus (rules/memory/
bug-classes/advancements, with any affected `*-INDEX.md` regenerated) **and**
Notion (factual Status + page-body progress note on every touched LC-#,
never a fabricated "done").

Permission is not optional ceremony: nothing is written to either surface
before MV has seen the classified batch and approved it. This mirrors the
same MV-approval gate the Auto-update protocol already states for the Claude
corpus — this rule's addition is making the Notion half equally mandatory and
making the *whole loop* something a validator can check ran, not something
that depends on remembering.

## Why

Two failure modes, one mechanism. First: a session's hard-won lessons —
this project's exact bug-classes 1-4 — evaporate if nobody writes them down,
and the next session re-discovers them at full cost. Second, and specifically
named by MV: Notion is the canonical to-do source Claude Code reads *before*
acting on any LC-# (`CLAUDE.md` Step 0). If a session's actual progress is
never written back — or worse, an invented "done" is written back — the next
session inherits a corrupted starting point and either redoes settled work or
trusts a false completion. MV's own words: "nothing gets left behind."

This rule exists because both failure modes are cheap to produce by doing
nothing, and this project has already paid for the first one twice in one
session (two `.agents/memory` files drifted OPEN-vs-fixed before anyone
checked; see `bug-classes.md` Class 2).

---

**FAIL condition:** a session that (a) modified a file matching a money-path
FAIL condition, or (b) worked on a task tied to a Notion Build Action Items
row, and closed without running `/wrap-session` — evidenced by no
corresponding Claude-corpus write (rule/memory/bug-class/advancement) *or*
Notion write-back for that session's work, when the reflection step would
have surfaced something to record. A session that genuinely produced no
durable learning is not a violation — `/wrap-session` saying so explicitly is
compliance, not a shortcut around it.

**WHERE-checked:** the `Stop` hook (`scripts/governance/wrap-session-reminder.sh`)
fires an advisory reminder whenever uncommitted or recently-committed changes
touch a money-path pattern; `/wrap-session`'s own Step 5 runs
`validate-all.sh` as its close-out check. There is no mechanical detector for
"a reflection step was honestly performed" — that half is `self-audit`,
carried by the skill's own Step 1-4 structure and MV's presence at the
permission gate (Step 3).

**Enforcement strength:** `mechanical` (Stop-hook reminder fires
unconditionally on the trigger condition; `validate-all.sh` is a real exit
code) + `self-audit` (whether the reflection was honest, and whether a
Notion write-back is factually accurate, are judgments no grep can make —
this is the same limit `validate-silent-failure.sh` already documents for
"is this default reassuring").
