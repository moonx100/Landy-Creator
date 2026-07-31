# Rule: Redact PII before every inference call

## What the rule requires

No text containing personal data leaves for an LLM without passing through
`landy.redaction.redact()` first. This binds **every** `chat_complete()` call
site without exception — analysis, summary, materiality, email draft, and any
future one.

The redaction contract: NIK, NPWP, bank account numbers, phone numbers, email
addresses, and street-address fragments are replaced with stable indexed tokens
(`[NIK_1]`, `[EMAIL_2]`, …) whose mapping is persisted per version in
`redaction_mappings` and re-expanded only at export time. Party and company names
are deliberately preserved — the model needs them for coherent analysis — and are
covered by the beta privacy notice rather than by tokenisation.

A new `chat_complete()` call site is not complete until its input path is traced
back to a `redact()` call.

## Why

The inference call, not the file at rest, is the material cross-border transfer
of personal data under UU PDP. Contracts uploaded by creators carry counterparty
NIK, NPWP, bank details and addresses — data of people who never consented to
LANDY processing it. Redaction is simultaneously the data-minimisation measure,
the transfer-risk mitigation, and a token-cost reduction; there is no trade-off to
weigh.

**This rule fails on a clean checkout today.** `analysis/pipeline.py` redacts
correctly (lines 142, 171). `diff/materiality.py` does not: it batches clause text
from `diff/compute.py`, which documents that it deliberately uses *original,
non-redacted* text, and sends it straight to `chat_complete()`. The diff path
therefore ships raw PII to the provider. Logged in
`.agents/memory/redaction-diff-path-gap.md`; this is the highest-priority
correctness item in the governance layer.

---

**FAIL condition:** any `chat_complete(` call site under
`artifacts/landy-api/` whose enclosing module neither imports
`landy.redaction.redact` nor receives input demonstrably produced by a redacted
upstream, as recorded in `scripts/governance/redaction-exempt.txt` with a written
justification per entry.

**WHERE-checked:** `scripts/governance/validate-redaction-before-inference.sh`
(enumerates every `chat_complete(` call site, resolves each to its module, and
requires a `redact` import or an allowlist entry) + `/review-gate` self-audit
tracing the actual data path, since a module-level import is necessary but not
sufficient.

**Enforcement strength:** `mechanical` (call-site enumeration) + `self-audit`
(data-flow tracing).
