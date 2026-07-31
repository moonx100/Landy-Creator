# Rule: Real OOXML tracked changes, never simulated

## What the rule requires

Redlined DOCX output uses genuine OOXML revision markup — `<w:ins>` and `<w:del>`
elements carrying `w:id`, `w:author`, and `w:date`, with deleted text in
`<w:delText>` — so that a reviewer opening the file in Word can **accept or
reject each change individually**.

Explicitly forbidden as a redline mechanism: blue/bold formatting to signify an
insertion, red/strikethrough formatting to signify a deletion, coloured
highlighting, or any run-property styling used as a stand-in for revision markup.
Formatting may accompany real revision markup; it may never replace it.

The same applies in reverse on ingest: `tracked_changes.py` reads `w:ins`/`w:del`
when a user uploads a contract that already carries the other side's revisions.

## Why

A simulated redline fails visibly in front of exactly the audience Creator is
built to impress. The recipient of a creator's redline is usually brand-side or
agency in-house counsel. They will open it in Word and reach for Review → Accept
All. Nothing will happen, because there is nothing to accept — just coloured text
they must now retype by hand. The creator looks amateurish, and by extension so
does the lawyer whose persona shipped the tool.

This is currently **implemented correctly** (`export/docx_export.py` builds real
`w:del`/`w:ins` elements and its module docstring already states the prohibition).
This rule is a **regression guard**: the simulated-redline approach was proposed
in an earlier external handoff and rejected, and it is the obvious shortcut for
anyone adding a new export format under time pressure.

---

**FAIL condition:** (a) an export path under
`artifacts/landy-api/landy/export/` that emits insertion/deletion semantics
without `w:ins`/`w:del` elements; or (b) the appearance of
strikethrough/colour-as-redline constructions (`w:strike`, `w:color` used to mark
a deletion, highlight-as-insertion) in an export generator; or (c) loss of
`w:author`/`w:date` attributes, which reviewers rely on to attribute changes.

**WHERE-checked:** `scripts/governance/validate-tracked-changes.sh` (requires
`w:ins`/`w:del`/`w:delText` construction in export generators; flags
`w:strike`/`w:color`/`w:highlight` appearing in a revision context) +
`/export-gate` self-audit — open the generated DOCX in Word and confirm
Accept/Reject All is live.

**Enforcement strength:** `mechanical` (markup presence + anti-pattern grep) +
`self-audit` (a real Word round-trip on the generated file).
