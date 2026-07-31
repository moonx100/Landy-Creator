---
name: export-gate
description: Verify the LANDY Creator export path — real OOXML tracked changes, PII re-expansion correctness, disclaimer presence, and tenant isolation on the fetch — before a redlined DOCX or negotiation email leaves the platform. Use on "/export-gate", "check the export", "verify the redline", after any change to export, docx_export, email_draft, tracked_changes, or doc_comments.
---

# /export-gate — the outbound-artifact gate

RED-tier. Everything this gate covers **leaves the platform** and is read by a
third party — usually brand-side or agency in-house counsel. An error here is not
just wrong, it is wrong in front of the audience whose respect the product is
trying to earn on MV's professional name.

## Mechanical (gated)

1. `bash scripts/governance/validate-tracked-changes.sh`
2. `bash scripts/governance/validate-legal-advice-framing.sh`
3. `bash scripts/governance/validate-tenant-isolation.sh`
4. `bash scripts/governance/compliance-eval.sh .claude/skills/export-gate/rubric.txt artifacts/landy-api/landy/export/docx_export.py`

## Self-audit (judgment — confirm and record)

**The Word round-trip — do this, do not reason about it**
- Generate a redlined DOCX. Open it in Word (or LibreOffice with track-changes on).
- Confirm Review → Accept All and Reject All both act on every change.
- Confirm each revision shows an author and a date.
- If changes appear as coloured text that Accept All ignores, the export is a
  simulated redline and must not ship.

**Redaction re-expansion**
- Confirm every `[NIK_n]` / `[EMAIL_n]` / `[BANK_n]` token is expanded in the
  exported artifact — a leaked placeholder token in a document sent to a brand is
  a visible defect and an implicit admission of what was sent to the model.
- Confirm the reverse: no token expands to the *wrong* original. Token stability
  is per-version; check a document with two versions.

**Disclaimer**
- Confirm the disclaimer survives into the artifact itself, not just the UI that
  produced it. The DOCX and the email are read outside the app, where the banner
  does not exist.
- Confirm the negotiation email frames itself as a negotiation position, not as
  counsel's demand. It will be read as coming from the creator.

**Tenant isolation on the fetch**
- Every row the export assembles — version, clauses, flags, diffs, redaction map
  — must be fetched under an explicit `user_id` predicate. RLS will not catch a
  mistake here; see `.agents/memory/rls-superuser-constraint.md`.

## Output

Short report: mechanical PASS/FAIL, the result of the actual Word round-trip
(state which application you opened it in), token-expansion spot checks, and any
item needing MV's review before the artifact is allowed out.
