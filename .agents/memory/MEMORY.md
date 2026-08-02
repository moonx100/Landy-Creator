# LANDY Creator — memory index

The project's second brain. **Evidence, not law** — see the Rule Promotion
Boundary in `CLAUDE.md`. A note here informs judgment; it does not constrain a
future session. If a finding must bind, promote it to `.claude/rules/` with a
validator.

Append, don't delete. Supersede inline with a dated line.

## Constraints

- [Replit DB superuser RLS constraint](rls-superuser-constraint.md) — DATABASE_URL is a Postgres superuser; `bypassrls=True`; explicit `WHERE user_id=:uid` is the real isolation layer. → bound by `.claude/rules/tenant-isolation.md`

## Open findings (gates that fail on a clean checkout)

- (none as of 2 Aug 2026 — validate-all is ALL PASS on branch fix/unknown-state-lc41)

## Resolved findings (kept for audit trail)

- [Redaction gap on the diff path](redaction-diff-path-gap.md) — RESOLVED 2 Aug 2026 by PR fix/redaction-all-channels; `_format_batch()` now redacts via the version-scoped mapping.
- [Extraction coverage gap](extraction-coverage-gap.md) — RESOLVED by PR fix/extraction-table-coverage; real floors + coverage ratios in `extraction.py`.
- [Materiality default gap](materiality-default-gap.md) — RESOLVED 2 Aug 2026 by the LC-41 unknown-state migration (nullable materiality + classification_status, joint CHECK).

## Decisions

- [Governance convention](governance-convention-decision.md) — why `.claude/` and `.agents/` both exist and neither absorbs the other.
- [Unified unknown-state pattern (LC-41)](unknown-state-pattern.md) — value vs. operational status are separate, jointly CHECK-constrained fields; no human-lawyer framing in Creator copy; >50%-failed = failed job + quota refund + carry-forward retry.
