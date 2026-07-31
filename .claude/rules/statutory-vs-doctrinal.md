# Rule: Statutory vs. doctrinal, always labeled

## What the rule requires

Any authority claim must record whether it is **codified statute** (with the
governing article) or **doctrinal inference**. The two are never blended, and a
doctrinal claim is never rendered to a user in language that implies statutory
force.

Concretely: `statutes.tier_basis` classifies the tier; `citations.basis`
classifies each citation. Permitted values are `statutory` (accompanied by an
article reference) or `doctrinal` (explicitly marked). `NULL` is permitted for an
unfilled slot — an unclassified *filled* slot is not.

The POJK / SEOJK / Peraturan-Menteri relative ranking is **not codified**. It
must not be hardcoded, ranked numerically, or presented as statutory anywhere.

## Why

This is the discipline the whole LANDY project rests on, and the thing that
distinguishes it from a general-purpose chatbot with a legal prompt. Presenting
an inference as statute is a category error that mis-states legal authority — the
money-path failure in its purest form. Creator's mini-corpus (KUHPerdata, UU Hak
Cipta, UU Merek, UU PDP, UU Perlindungan Konsumen, UU ITE, UU 24/2009) is almost
entirely UU-tier, so it exercises the Pasal 7 ladder and barely touches the open
Pasal 8 ranking question — but the labeling discipline applies from record one.

Note the field is `citations.basis`, not `citation_basis` (the incoming handoff
named it imprecisely).

---

**FAIL condition:** (a) a `statutes` row written with a non-NULL `tier_rank` but a
NULL or unclassified `tier_basis`; or (b) a `citations` row with a non-NULL
`provision_id` or `citation_text` and a NULL/unclassified `basis`; or (c) a tier
rank integer literal hardcoded in application code rather than read from the
statute record; or (d) any user-facing string presenting a doctrinal inference in
statutory language.

**WHERE-checked:** `scripts/governance/validate-hierarchy.sh` (grep for hardcoded
`tier_rank` literals; assert `basis`/`tier_basis` are written wherever their
companion fields are) + `/review-gate` self-audit on rendered authority language.

**Enforcement strength:** `mechanical` (literal grep + companion-field check) +
`self-audit` (the statutory-vs-doctrinal judgment itself is MV's).
