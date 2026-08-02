---
name: Materiality default gap
description: On LLM failure, diff/materiality.py persists "immaterial" rather than surfacing that classification was unavailable.
---

# A failed classification is stored as a clean result

## The finding

`landy/diff/materiality.py` returns `("immaterial", "Klasifikasi tidak tersedia")`
on parse failure (line 104), on batch failure (line 109), and on LLM failure
(line 211). Its own docstring states it "never raises."

The reason string is honest. The classification field is not — and downstream
consumers read the field, not the reason. A change that could not be classified
is stored, queried, and rendered identically to a change that was classified and
found immaterial.

There is currently no `needs_review` / `unavailable` state anywhere in the domain
vocabulary, so a failure has nowhere honest to land even if the code wanted to
record one.

## Why it matters

This is the money-path asymmetry stated in `CLAUDE.md`, in its exact form. A
creator comparing v1 and v2 of a brand contract reads "tidak ada perubahan
material" and stops looking. They cannot tell that the model call failed. The
counterparty's newly inserted exclusivity clause is sitting in the diff,
classified `immaterial` by a fallback branch.

"Never raises" is the right instinct applied to the wrong field. The pipeline
*should* survive an LLM failure — it should not survive it by lying about the
result.

## Candidate fix

1. Add a third materiality value — `needs_review` (or `unavailable`) — to the
   schema CHECK constraint, the Pydantic model, and the UI.
2. Return it on every failure branch, carrying the existing reason string.
3. Render it distinctly: a change awaiting review must be visually louder than an
   immaterial one, not quieter.
4. Keep the non-raising behaviour. Degrade toward visibility, never toward silence.

## Status

**RESOLVED** — see the dated section below. (Originally opened 31 Jul 2026;
`scripts/governance/validate-silent-failure.sh` now passes.)

Related: `.claude/rules/silent-failure.md`, `MEMORY.md`.

---

## RESOLVED — 2 Aug 2026 (branch fix/unknown-state-lc41, the LC-41 migration)

Implemented as one instance of the unified unknown-state pattern, not the
original third-enum candidate fix: `materiality` is nullable with companion
`classification_status ('ok'|'low_confidence'|'failed')` + `classification_error`,
jointly CHECK-constrained (`version_diffs_materiality_state`) so "failed but
labelled immaterial" is unrepresentable (migration 0010). All four fallback
sites in `diff/materiality.py` now return `MaterialityResult(status='failed',
materiality=None)`. Frontend `MATERIALITY_CONFIG` is a total mapping (no `??`);
unclassified rows render loud amber "Belum Terklasifikasi"; the all-clear
sentence is gated on `review_complete`. Forced-failure semantics locked by
`tests/test_unknown_state.py`. `validate-silent-failure.sh` checks #3/#4 pass.
Full decision record: Build Action Items LC-41.
