# Rule: The unknown state is representable — absence of an answer is never a negative answer

> **PROPOSED 2026-08-02 — binds only after MV sign-off on the LC-41 PR.**
> Decided design: Build Action Items LC-41 (MV decisions recorded there).

## What the rule requires

Every classification or parse step whose output a user can read must have a
**representable, persisted, rendered** state for "we don't know" — and the
failure of the step must land in that state, never in a benign value.

Concretely, per site topology:

- **Enum-value sites** (e.g. `version_diffs.materiality`): the semantic value
  is nullable; a companion `*_status` (`ok | low_confidence | failed`) +
  `*_error` pair records the operational outcome; a **joint CHECK
  constraint** makes "failed but valued" and "ok but NULL" unrepresentable.
- **No-row-on-failure sites** (risk flags): a per-attempt run record
  (`analysis_domain_runs`) exists for every attempt, so "no findings" is only
  derivable from a complete set of `ok` runs.
- **Artifact/parse sites** (extraction, tracked changes, comments, summary):
  a `*_ok`/`*_status` + note pair on the owning row, following the
  `extraction_ok`/`extraction_note` precedent, travelling parse → storage →
  API → render.
- **Aggregate claims** ("tidak ada perubahan material", "tidak ada temuan
  risiko", counts): derived only from a server-computed completeness signal
  (`review_complete`); counts computed by counting, never by subtraction; the
  all-clear string must be structurally unreachable while any contributing
  check is not `ok`.
- **Frontend mappings** are total and exhaustive — no `lookup[x] ?? DEFAULT`
  into a different config entry; an unrecognised state renders loudly
  (amber/explicit), never as the quietest style.
- **User-facing copy** for unknown states routes to the *user* with a fixable
  action ("Klausul tidak terbaca — pastikan dokumen dalam format .docx dan
  terstruktur") and never implies a human-lawyer review step (MV constraint:
  Creator is not a legal-opinion service).

## Why

Six independent sites once wrote a failed result as a benign valid value
(materiality→immaterial, finding_type→none, severity→info,
tracked-changes→has_changes=False, comments→[], summary→raw slice). Each was
individually plausible; together they meant every failure degraded toward a
reassuring answer — the exact inversion of the money-path asymmetry. The one
place the schema got this right from day one, `statutes.status DEFAULT
'unverified'`, existed because a rule forced it. This rule exists so the next
classification feature cannot ship without its unknown state.

---

**FAIL condition:** (a) a failure/fallback branch under `artifacts/landy-api/`
assigning a substantive domain value (`"immaterial"`, `"info"`, `"none"`,
`has_changes=False`, `[]`-as-answer, raw-text-as-summary) without a surfaced
status on the same path; (b) a schema change that drops or weakens a joint
value/status CHECK constraint or a `*_status` column; (c) a `.ts`/`.tsx`
config-map lookup coalesced into a different config entry (`?? CONFIG.x`);
(d) an all-clear string rendered without consulting the completeness signal.

**WHERE-checked:** `scripts/governance/validate-silent-failure.sh` (Python
shapes + vocabulary) + `scripts/governance/validate-silent-failure-web.sh`
(TS map-lookup coalescing + all-clear gating) +
`artifacts/landy-api/tests/test_unknown_state.py` (forced-failure semantics
the greps cannot see) + `/review-gate` self-audit.

**Enforcement strength:** `mechanical` (greps + CHECK constraints + tests) +
`self-audit` (whether a given default is reassuring, and register of new
sites, is a judgment).
