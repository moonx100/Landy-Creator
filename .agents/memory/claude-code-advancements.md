---
name: Claude Code advancements — internal tooling/governance queue
description: Persistent ledger of Claude Code's own workflow/governance/tooling improvements for LANDY Creator — shipped, in progress, and deliberately deferred with revisit triggers.
---

# Claude Code advancements

This is the dedicated home for ideas about **how Claude Code works on this
project** — governance mechanisms, workflow rituals, internal tooling — as
distinct from `[[bug-classes.md]]` (which catalogs *bugs*, not features) and the
rest of `.agents/memory/` (which catalogs *findings about the product*).

Modelled on the F4TALITY project's `interaction-learnings.md`: a context-dense,
append-only ledger. Referenced from `CLAUDE.md`'s Auto-update protocol. This file
itself is registered for INDEX auto-sync (`scripts/index-registry.json`) once it
grows past the threshold in `scripts/src/index-headings.ts`.

**Evidence, not law** — an entry here does not bind a future session. A shipped
item binds only through its own rule/validator/hook; this file just tracks that
it exists and why.

---

## Shipped

- **Gate-first rule authoring** (What/Why + FAIL condition + WHERE-checked +
  Enforcement strength) — `validate-gate-first.sh`. Predates this ledger.
- **Domain-blind second-brain hygiene** — `validate-bridge-health.sh` (orphan
  context check on `.agents/memory`). Predates this ledger.
- **2026-08-02 — Governance apparatus** (this session, branch
  `feat/governance-apparatus`), inspired by a structural review of the F4TALITY
  project's `.claude/` ruleset:
  - Bug-class registry (`bug-classes.md`) — this queue's sibling.
  - This advancements queue.
  - Enforcement Registry table (`.claude/rules/README.md`) +
    `validate-enforcement-registry.sh` drift guard.
  - Memory staleness guard (`validate-memory-sync.sh`).
  - INDEX auto-sync machinery (`scripts/src/index-headings.ts` +
    `index-registry.json` + `validate-index-sync.sh`).
  - Money-path `PreToolUse` hard-stop hook (`money-path-guard.sh`).
  - **Session-close reconciliation ritual** (`/wrap-session` skill +
    `session-reconciliation.md` binding rule) — the centerpiece: at the end of
    every money-path-touching session, present errors/lessons, get MV's
    permission, then commit the learnings to *both* the Claude corpus (rules /
    memory / bug-classes / advancements / INDEX) and Notion (factual
    status + page-body progress note on every touched Build Action Items row).
    Motivation: this same session hand-discovered two stale memory files and a
    real mobile bug a mechanical gate later caught in one pass — the ritual
    makes that reconciliation pass standard instead of incidental.

## In progress

*(none — update when a queued item below is picked up)*

## Queued / deferred

Right-sized for a solo-operator, 10–20-user beta: F4TALITY-scale ceremony that
would cost more than it returns today. Each entry names its **revisit
trigger** so the deferral is a decision, not an omission.

- **Named subagents with model/effort floors** (F4TALITY's
  `.claude/agents/*.md` + `CLAUDE_CODE_SUBAGENT_MODEL` env floor).
  *Revisit when:* a second regular contributor or a second write path (beyond
  Replit + Claude Code Desktop) starts dispatching subagents on the money-path.
- **Delegation tiering / dispatch discipline** (F4TALITY §10, §19 — formalised
  rules for when to fan out to subagents vs. work solo).
  *Revisit when:* task volume regularly needs multi-agent fan-out, not just
  occasional Explore-agent research.
- **Full `/post-session` DB-audit workflow** (F4TALITY's phased,
  human-gated-at-every-destructive-step DB reconciliation command).
  *Revisit when:* the corpus/ingest pipeline (LC-40, currently blocked) is live
  and produces its own DB-integrity failure modes worth a dedicated ritual.
- **INDEX auto-sync for the `.claude/rules/*.md` files themselves.**
  *Revisit when:* any single rule file exceeds ~250 lines (today the longest is
  a single screen — indexing a one-screen file is overhead, not clarity).
- **PreToolUse DENY hooks beyond the money-path guard** (e.g. gating exports,
  migrations, or Notion writes the way F4TALITY gates deep-analysis reports).
  *Revisit when:* the money-path guard (shipped this session) proves its value
  in practice and a second high-risk surface emerges that needs the same
  hard-stop treatment.

---

Related: `CLAUDE.md` (Auto-update protocol), [[bug-classes.md]], `[[MEMORY.md]]`.
