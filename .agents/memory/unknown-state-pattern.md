# The unified unknown-state pattern (LC-41) — decision record

**Date:** 2 Aug 2026 · **Decided by:** MV (via Claude Code Phase A session) ·
**Implemented on:** branch `fix/unknown-state-lc41`, migrations 0009 + 0010.

## The decision

Six sites wrote a failed result as a benign value (materiality→immaterial,
finding_type→none, severity→info, tracked-changes→has_changes=False,
comments→[], summary→raw slice). One pattern now covers all six: the semantic
value and the operational outcome are separate fields, jointly constrained so
the dishonest combination is unrepresentable in the database.

- Enum sites: nullable value + `*_status` + `*_error`, joint CHECK.
- No-row-on-failure sites (risk flags): per-attempt `analysis_domain_runs`.
- Artifact sites (tc/comments/summary): status+note columns, following the
  `extraction_ok`/`extraction_note` precedent.
- Aggregates: server-computed `review_complete`; counts by counting, never
  subtraction; all-clear strings unreachable while any check ≠ ok.

## MV's constraints (important for future copy/design)

- **No human-lawyer framing in Creator.** Unknown states route to the *user*
  with a fixable action ("Klausul tidak terbaca — pastikan dokumen dalam
  format .docx dan terstruktur"). Legal-opinion service = LANDY Original/Crew.
- `low_confidence` is reserved in the CHECK now, emitted later (gated on the
  eval set) — no second migration needed to enable it.
- >50% domains failed ⇒ job `failed` + atomic quota refund (idempotent via
  `analysis_jobs.quota_refunded`) + FU message; retry carries forward
  successful domain results (`_fetch_carryover_domains`) and re-runs only
  failed checks; unchecked risk categories listed by name.
- Failed LLM calls write `usage_events` rows with NULL tokens — never a local
  estimate; billed-but-discarded completions keep their real counts
  (status='failed', failure_stage).

## Traps for future sessions

- `tests/test_unknown_state.py` is the semantic gate — greps cannot see
  "immaterial with status ok". Keep it green.
- The web/mobile render layer is governed by
  `validate-silent-failure-web.sh` (map-lookup `??` coalescing + all-clear
  gating). Cosmetic raw-key label fallbacks carry `silent-failure-ok` pragmas.
- Downgrading migration 0010 DELETEs rows with NULL materiality (they are
  failed classifications the old schema cannot express).
- Rule promotion: `.claude/rules/unknown-state.md` was PROPOSED in the LC-41
  PR; it binds only after MV sign-off.
