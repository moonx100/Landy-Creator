# LANDY Creator — memory index

The project's second brain. **Evidence, not law** — see the Rule Promotion
Boundary in `CLAUDE.md`. A note here informs judgment; it does not constrain a
future session. If a finding must bind, promote it to `.claude/rules/` with a
validator.

Append, don't delete. Supersede inline with a dated line.

## Constraints

- [Replit DB superuser RLS constraint](rls-superuser-constraint.md) — DATABASE_URL is a Postgres superuser; `bypassrls=True`; explicit `WHERE user_id=:uid` is the real isolation layer. → bound by `.claude/rules/tenant-isolation.md`

## Open findings (gates that fail on a clean checkout)

- [Redaction gap on the diff path](redaction-diff-path-gap.md) — `diff/materiality.py` sends non-redacted clause text to the LLM. Highest-priority correctness item. → `.claude/rules/redact-before-inference.md`
- [Extraction coverage gap](extraction-coverage-gap.md) — `extraction_ok` rests on `bool(text.strip())`; a 51-character extraction from a 20-page contract passes. → `.claude/rules/extraction-coverage.md`
- [Materiality default gap](materiality-default-gap.md) — a failed classification is persisted as `"immaterial"`. → `.claude/rules/silent-failure.md`

## Decisions

- [Governance convention](governance-convention-decision.md) — why `.claude/` and `.agents/` both exist and neither absorbs the other.
