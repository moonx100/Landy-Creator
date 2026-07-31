---
name: Governance convention decision — .claude and .agents coexist
description: Why LANDY Creator runs two agent-facing directories rather than standardising on one.
---

# Two directories, one boundary

## The decision

`.claude/` holds **law**: `CLAUDE.md` (router), `.claude/rules/` (ten gate-first
rules), `.claude/skills/` (the `/review-gate` and `/export-gate` compliance
gates), `.claude/settings.json` (hooks).

`.agents/memory/` holds **evidence**: findings, constraints, decisions — this
directory.

`.agents/skills/` is left **completely untouched**.

Neither directory absorbs the other. This was the main open question in the
incoming handoff (§7.1) and the answer is "bridge", not "standardise".

## Why not standardise on `.agents/`

Claude Code natively reads `CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, and
`.claude/settings.json`. Nothing in `.agents/` is loaded automatically. Putting
binding rules there would mean they bind only when someone remembers to mention
them — which is the failure mode the gate-first discipline exists to eliminate.

## Why not standardise on `.claude/`

`.agents/skills/` is lockfile-managed. `skills-lock.json` pins four external
skills (`agent-tools`, `frontend-design`, `ui-ux-pro-max`, `web-design-guidelines`)
by `computedHash` against their upstream GitHub sources. Moving, renaming, or
editing those files breaks hash verification, and the next `skills add` sync
reverts the change. That directory is vendored dependency, not project source —
treat it the way you treat `node_modules`.

`.agents/memory/` was kept in place for a smaller but real reason: moving
`rls-superuser-constraint.md` would break the relative link from `MEMORY.md` and
detach the note from the history that produced it. It is also, on inspection, a
better-designed memory layer than landy-workspace's `docs/second-brain/` — a
single index plus standalone notes, rather than four fixed-schema tables that
force every finding into a row.

## The unexpected upside

The split maps exactly onto the Rule Promotion Boundary that landy-workspace
already declared — law binds, evidence informs. Creator now has that boundary
expressed as directory structure rather than as a paragraph people have to
remember. The two conventions turned out to be complementary rather than
competing.

## Consequence

`docs/second-brain/` is **not** created in this repo. landy-workspace's
`validate-bridge-health.sh` was re-pointed to `.agents/memory` instead.

Decided 31 Jul 2026. Related: `MEMORY.md`, `CLAUDE.md`.
