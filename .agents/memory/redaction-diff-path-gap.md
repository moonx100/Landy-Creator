---
name: Redaction gap on the version-diff path
description: diff/materiality.py sends non-redacted clause text to the LLM. The analysis path redacts correctly; the diff path does not.
---

# Non-redacted PII reaches the model on the diff path

## The finding

`landy/analysis/pipeline.py` redacts correctly before inference (lines 142, 171).
`landy/diff/materiality.py` does not. It batches clause text via `_format_batch()`
and calls `chat_complete()` at line ~178 with no redaction step.

The upstream is explicit about why: `landy/diff/compute.py` documents that the
diff deliberately uses *original, non-redacted* clause text, because token-level
diffing against redacted text would produce spurious changes whenever token
numbering shifted between versions. That reasoning is sound for **diffing**. It
was not re-examined before the same text was handed to an **inference call**.

## Why it matters

Uploaded creator contracts carry counterparty NIK, NPWP, bank account numbers,
addresses and phone numbers — personal data of people who never consented to
LANDY processing it, let alone to its transfer to an overseas inference provider.
Under UU PDP the inference call, not the file at rest, is the material
cross-border transfer. The diff path therefore ships exactly what the redaction
module exists to prevent.

Severity is raised by the fact that this is the *second version* path: by
definition it runs on contracts the user is actively negotiating, i.e. the ones
most likely to be fully populated with real party details.

## Candidate fixes (MV to choose — do not pick silently)

1. **Redact at the materiality boundary.** Diff on original text; redact each
   entry immediately before `_format_batch()`. Smallest change, preserves diff
   fidelity, costs nothing. Recommended.
2. **Redact both versions with a shared, version-stable token map** before
   diffing. Cleaner conceptually; requires the mapping to be stable across
   versions, which the current per-version scheme does not guarantee.
3. Exempt the path with justification in `scripts/governance/redaction-exempt.txt`.
   **Not recommended** — there is no PDP argument that survives contact with a
   regulator here.

## Status

**RESOLVED** — see the dated section below. (Originally opened 31 Jul 2026;
`scripts/governance/validate-redaction-before-inference.sh` now passes.)

Related: `.claude/rules/redact-before-inference.md`, `MEMORY.md`.

---

## RESOLVED — 2 Aug 2026

Fixed by PR `fix/redaction-all-channels` (commit `3252e3b`, merged `fce7cb3`)
via candidate fix #1 as recommended: `_format_batch()` redacts before/after
text through the version-scoped mapping (`materiality.py:80-86`), the mapping
is fetched at L183 and persisted at L240-242, and `classify_materiality` gained
a `version_id` parameter. `validate-redaction-before-inference.sh` passes.
Verified against HEAD `6b7076a` during the LC-41 session.
