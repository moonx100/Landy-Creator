# Rule: No silent near-empty extraction

## What the rule requires

`extraction_ok` must mean *the document was extracted*, not *the extractor
returned a non-empty string*. Every extraction path must apply a coverage check
before declaring success, and must surface a failure the user can see when
coverage is implausible.

Minimum shape of the check:

- an absolute floor on extracted characters;
- a plausibility ratio against an independent signal of document size — page
  count for PDF, paragraph/element count for DOCX, byte size as a last resort;
- OCR paths additionally carry `accuracy_warning` (already implemented) and are
  held to the same coverage floor.

On failure: `extraction_ok=False`, a populated `extraction_note`, and a surfaced
state. Never a short string with `extraction_ok=True`.

## Why

`bool(full_text.strip())` is the current test at four call sites in
`extraction.py` (lines 85, 118, 148, 192). A scanned PDF whose text layer yields
51 characters of header junk from a 20-page brand agreement passes it. The
pipeline then analyses 51 characters, finds no risks in them, and returns a clean
report on a contract nobody read.

That is the worst failure this product can produce — worse than a crash, worse
than a wrong flag — because it is indistinguishable from success at every layer
above it and it terminates in a creator signing an unreviewed contract. This rule
exists specifically for that scenario.

---

**FAIL condition:** any code path in `artifacts/landy-api/landy/extraction.py`
(or a successor extractor) that sets `extraction_ok=True` on the basis of a
non-empty/whitespace test alone, with no character floor and no
coverage-ratio check against page/element/byte count.

**WHERE-checked:** `scripts/governance/validate-extraction-coverage.sh`
(requires a named coverage constant and a ratio/floor comparison in the extractor,
and flags bare `bool(...strip())` success assignments) + `/review-gate` self-audit
on a real scanned PDF fixture.

**Enforcement strength:** `mechanical` (constant + comparison presence) +
`self-audit` (threshold calibration is empirical — tune against real creator
contracts, not invented numbers).
