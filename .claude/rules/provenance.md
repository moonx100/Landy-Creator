# Rule: Source-first + provenance

## What the rule requires

Two halves.

**Corpus half (active at schema level, dormant at data level):** every `statutes`
record carries `source_url`, `retrieved_date`, and `sha256`. The v1 corpus is
deliberately empty — the columns exist and must not be dropped or made nullable
in a later migration.

**Answer half (active now):** every risk flag that rests on a legal proposition
must carry its authority in `citations` — `provision_id` where the corpus
supports it, `citation_text` otherwise — or carry **no citation at all** rather
than a fabricated one. An empty citation slot is honest; an invented Pasal number
is a fabrication a lawyer-built product cannot survive shipping.

Retrieval is preferred over generation. The model must never be prompted in a way
that invites it to supply a statute reference from parametric memory.

## Why

Creator's credibility rests on MV's standing as a former regulator and practising
advocate. One hallucinated `Pasal 1320 KUHPerdata` in a redline sent to a brand's
in-house counsel costs more than every feature in the backlog is worth.
`citation_text` is `NULL` in v1 by design — the citation layer attaches later
without schema rework. Until it does, flags carry rationale, not authority, and
must not pretend otherwise.

---

**FAIL condition:** (a) a migration that drops or relaxes `source_url` /
`retrieved_date` / `sha256` on `statutes`; or (b) an LLM prompt under
`artifacts/landy-api/landy/` that instructs the model to produce a statute /
Pasal / Ayat reference while the corpus is empty; or (c) a user-facing surface
rendering a citation string that has no `provision_id` and no operator-verified
`citation_text`.

**WHERE-checked:** `scripts/governance/validate-provenance-schema.sh` (schema
columns) + `scripts/governance/validate-legal-advice-framing.sh` (prompt scan for
citation-invention instructions) + `/review-gate` self-audit on rendered flags.

**Enforcement strength:** `mechanical` (schema + prompt grep) + `self-audit`
(whether a rendered citation is grounded).
