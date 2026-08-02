---
name: Extraction coverage gap
description: extraction_ok is set from bool(text.strip()) — any non-empty string counts as success, so a near-empty extraction passes silently.
---

# Non-empty is not the same as extracted

## The finding

`landy/extraction.py` sets success from a bare non-emptiness test at four points
(lines 85, 118, 148, 192):

```python
ok = bool(full_text.strip())
```

There is no character floor and no ratio against page count, paragraph count, or
file size. A scanned PDF whose text layer yields a few dozen characters of header
junk from a twenty-page brand agreement returns `extraction_ok=True` with a
sha256, and proceeds into segmentation and analysis as a valid document.

## Why it matters

This produces the worst output the product can generate: **a clean review of a
contract nobody read.** It is worse than a crash and worse than a wrong flag,
because every layer above it behaves normally. Segmentation finds few clauses,
analysis finds no risks in them, the UI renders a tidy report, and the creator
concludes their contract is fine and signs it.

Nothing downstream can detect this. The check has to happen at extraction.

## Candidate fix

Add a named coverage constant and a two-part test:

- an absolute floor (documents below it are implausible as contracts);
- a ratio against an independent size signal — characters per PDF page,
  characters per DOCX paragraph, or characters per KB as a fallback.

On failure: `extraction_ok=False`, a populated `extraction_note`, and a state the
user can see. Do **not** invent the thresholds — calibrate them against real
creator contracts from the beta cohort. A threshold tuned on guesses will either
pass the failure it exists to catch or reject legitimate one-page agreements.

## Status

**RESOLVED** by PR `fix/extraction-table-coverage`. `extraction.py` now defines
`_MIN_CHARS=100`, `_MIN_COVERAGE_RATIO=0.5` (DOCX), `_MIN_CHARS_PER_PAGE=40`
(PDF), `_MIN_CHARS_PER_KB=0.5` (image) and checks them at every success branch
(verified against current `artifacts/landy-api/landy/extraction.py`,
2 Aug 2026). `scripts/governance/validate-extraction-coverage.sh` passes.

Related: `.claude/rules/extraction-coverage.md`, `MEMORY.md`.
