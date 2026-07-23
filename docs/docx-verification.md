# DOCX Export Verification Checklist

**Purpose:** Manual audit trail confirming LANDY Creator's DOCX export produces
genuine OOXML tracked changes that can be individually accepted and rejected in
Microsoft Word. This checklist satisfies spec §8a.

---

## Pre-conditions

- A LANDY Creator analysis has completed (job state = `done`).
- At least one `suggested_edit` exists with `accepted IS NOT FALSE`
  (i.e. accepted or undecided).
- The DOCX has been exported via `POST /api/documents/{doc_id}/versions/{ver_id}/export/docx`.
- The DOCX file has been downloaded and opened in **Microsoft Word 2016 or later**.
  (Google Docs does not accurately render OOXML revision markup.)

---

## Step 1 — Open the Tracked Changes Panel

1. In Word: **Review → Tracking → Show Markup → All Markup**
2. Confirm the **Revisions** pane shows individual insertions and deletions.
3. Each change should appear as a separate entry in the Revisions pane.

**Pass criterion:** The Revisions pane lists at least one insertion (`+`) and
one deletion (`-`) for each suggested edit that was included in the export.

**Fail indicator:** No entries in the Revisions pane, OR changes appear as
coloured/formatted text only (blue-bold / red-strikethrough). If the latter,
the export has produced fake formatting — this is a critical bug.

---

## Step 2 — Accept One Change Individually

1. In the Revisions pane, right-click the **first** change.
2. Select **Accept This Change**.
3. Confirm:
   - The deletion (`<w:del>`) disappears from the document.
   - The insertion (`<w:ins>`) becomes plain text.
   - All other changes remain unchanged and still appear in the Revisions pane.

**Pass criterion:** Exactly one change is accepted; all others unaffected.

---

## Step 3 — Reject One Change Individually

1. In the Revisions pane, right-click the **second** change (or any remaining change).
2. Select **Reject Change**.
3. Confirm:
   - The inserted text (`<w:ins>`) is removed.
   - The original deleted text (`<w:del>`) is restored.
   - The change disappears from the Revisions pane.

**Pass criterion:** Exactly one change is rejected; original text restored; others unaffected.

---

## Step 4 — Verify Word Comments

1. In Word: **Review → Comments → Show Comments**.
2. Each tracked change should have a linked comment balloon or appear in the Comments pane.
3. The comment text should contain the LANDY Creator rationale/note for the change.
4. Comment IDs should not conflict (no two comments with the same `w:id`).

**Pass criterion:** Every tracked change has exactly one associated comment.

---

## Step 5 — Verify Disclaimer Comment

1. Look for a comment at the very beginning of the document (position 0).
2. The comment text should read:
   > *"PENTING: Dokumen ini adalah informasi hukum dan panduan negosiasi, BUKAN
   > nasihat hukum. Dokumen ini BUKAN pengganti konsultasi dengan Advokat berlisensi.
   > Dihasilkan oleh LANDY Creator."*
3. The disclaimer paragraph itself should be formatted as disclaimer text (red italic).

**Pass criterion:** Disclaimer comment present at document start; text matches.

---

## Step 6 — Accept All / Reject All

1. **Review → Accept → Accept All Changes** — confirm document collapses to the
   revised version with no markup remaining.
2. Undo that action.
3. **Review → Reject → Reject All Changes** — confirm document reverts to the
   original clause text.

**Pass criterion:** Both operations complete without error; no orphaned markup.

---

## Step 7 — Comment-Only Edits (if applicable)

If the export log includes `comment_only_count > 0`, some edits could not be
expressed as clean tracked changes (original text not found verbatim).

1. Open the Comments pane: **Review → Comments → Show Comments**.
2. Look for comments titled "LANDY Creator — Usulan Perubahan".
3. These comments contain the original and proposed text.
4. Confirm no corresponding tracked change exists (the text is unchanged).

**Pass criterion:** Comment present, no tracked change markup, no fake formatting.

---

## Common Failure Modes

| Symptom | Root cause | Fix |
|---|---|---|
| No entries in Revisions pane | `<w:del>`/`<w:ins>` missing or malformed | Check document.xml in the DOCX zip |
| Changes are blue-bold or red-strikethrough | Fake formatting used instead of OOXML markup | Bug in `docx_export.py` — this must never happen |
| Word says "document is corrupted" | Invalid XML or missing namespace | Check XML well-formedness with `xmllint` |
| Comments not linked to changes | `w:id` mismatch between comment and range | Ensure `comment_id` matches in `commentRangeStart`, `commentRangeEnd`, and `commentReference` |
| Accept/reject does not work | Content type mismatch or settings.xml missing `<w:trackChanges/>` | Check `[Content_Types].xml` and `word/settings.xml` |

---

## XML Verification (Advanced)

To inspect the raw OOXML:

```bash
# Extract and inspect document.xml
unzip -p exported.docx word/document.xml | xmllint --format - | grep -A5 "w:del\|w:ins"

# Check comments
unzip -p exported.docx word/comments.xml | xmllint --format -

# Validate settings include trackChanges
unzip -p exported.docx word/settings.xml | grep trackChanges
```

Expected output includes `<w:del w:id=...>`, `<w:ins w:id=...>`, and `<w:trackChanges/>`.

---

*Last updated: Task #4 implementation. Any update to `landy/export/docx_export.py`
must be re-verified against this checklist.*
