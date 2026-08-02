# Rule: Silent failures are bugs — no reassuring defaults

## What the rule requires

Every extraction, LLM, analysis, and export step must log and surface its failure
states. A failure must never be written to the database or shown to a user as a
**substantive result**. In particular:

- A failed materiality classification must not be persisted as `"immaterial"`.
- A failed or near-empty extraction must not be persisted with `extraction_ok=True`.
- A failed risk analysis must not yield an empty flag list presented as "no risks found."
- No `except:` / `except Exception: pass` anywhere on these paths.

Where a step cannot complete, the correct degradation is an explicit
`needs_review` / `unavailable` state that is **visible to the user**, not a
plausible default.

## Why

This is the money-path asymmetry stated in `CLAUDE.md`. A creator reading "tidak
ada perubahan material" cannot distinguish *the model checked and found nothing*
from *the model call failed and the code filled in a default*. The second is a
missed material risk in a contract the user is about to sign. A reassuring
default on a failure path is the most dangerous line of code in this repo.

`diff/materiality.py` used to violate this on LLM failure, returning
`("immaterial", "Klasifikasi tidak tersedia")` despite documenting that it
"never raises." **Resolved 2 Aug 2026** by the LC-41 unknown-state migration —
see `.claude/rules/unknown-state.md` and
`.agents/memory/materiality-default-gap.md`. This is Class 1 in
`.agents/memory/bug-classes.md`: the reassuring-default shape recurs across
sites, which is why the fix generalised into its own rule rather than staying a
one-file patch.

---

**FAIL condition:** (a) a bare `except:` or `except ...: pass` under
`artifacts/landy-api/`; or (b) any failure/fallback branch that assigns a
substantive domain value — `"immaterial"`, `extraction_ok=True`, an empty
results list treated as success — without also setting a surfaced
review/unavailable flag on the same path.

**WHERE-checked:** `scripts/governance/validate-silent-failure.sh` (greps for
bare/silent excepts and for the known reassuring-default literals on except
branches) + `/review-gate` skill self-audit + code review.

**Enforcement strength:** `mechanical` (grep gate) + `self-audit` (whether a
given default is reassuring is a judgment the grep only approximates).
