---
name: review-gate
description: Verify the LANDY Creator contract-review path — extraction coverage, PII redaction before inference, silent-failure defaults, and information-not-advice register — before analysis output is trusted or shipped. Use on "/review-gate", "check the review path", "verify the analysis", after any change to extraction, segmentation, analysis, taxonomy, prompts, or the diff/materiality path.
---

# /review-gate — the analysis money-path gate

RED-tier. This gate covers everything between *a creator uploads a file* and *a
risk flag appears on screen*. A failure here reaches the user as a confident,
well-formatted, wrong answer.

Modelled on landy-workspace's `/ingest-check` **pattern** — mechanical rubric
plus self-audit — but nothing was copied: Creator has no acquisition path, so the
subject matter is entirely different.

## Mechanical (gated — nonzero exit blocks trusting the run)

1. `bash scripts/governance/validate-extraction-coverage.sh`
2. `bash scripts/governance/validate-redaction-before-inference.sh`
3. `bash scripts/governance/validate-silent-failure.sh`
4. `bash scripts/governance/validate-legal-advice-framing.sh`
5. `bash scripts/governance/compliance-eval.sh .claude/skills/review-gate/rubric.txt artifacts/landy-api/landy/extraction.py`

## Self-audit (judgment — confirm and record; the grep cannot do these)

**Extraction**
- Run a real scanned PDF and a real DOCX through the extractor. Compare extracted
  character count against visible page count. Would a 51-character result from a
  20-page contract be caught? If not, the coverage threshold is mis-tuned.
- Confirm an OCR path carries `accuracy_warning` *and* still meets the coverage floor.

**Redaction — trace the data, not the import**
- For every `chat_complete()` call site, follow the input variable backwards to
  its origin. A module-level `redact` import proves nothing about the actual path.
- The diff path is the known gap: `diff/compute.py` deliberately holds original
  text, and `diff/materiality.py` batches it straight to the model. Confirm the
  status of that gap before signing off.

**Failure register**
- For each failure branch, ask: *what does the user see?* If the answer is
  indistinguishable from a successful clean result, it is a silent failure
  regardless of what the log says.
- Confirm no classification, severity, or flag list defaults to the reassuring
  value on error.

**Legal register**
- Read three generated risk flags end to end. Do they *identify and explain*, or
  do they *determine and instruct*? Statements like "batal demi hukum" may be
  legally correct and still be the wrong register for a user-facing surface.
- Confirm no flag asserts a Pasal reference while the corpus is empty.

## Escalate to MV, do not resolve

Any question of Indonesian legal substance — whether a clause really is void,
whether a risk is correctly rated CRITICAL, whether a `negotiation_ask` is sound.
MV is the former regulator and practising advocate; that is their call, not the
model's.

## Output

Short report: mechanical PASS/FAIL table, self-audit findings, the extraction
coverage numbers you actually measured, and an explicit list of items needing MV's
legal verification. Do not declare the review path trusted while any mechanical
check fails.
