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

OPEN as of 31 Jul 2026. `scripts/governance/validate-silent-failure.sh` fails on
both this and the missing `needs_review` vocabulary.

Related: `.claude/rules/silent-failure.md`, `MEMORY.md`.
