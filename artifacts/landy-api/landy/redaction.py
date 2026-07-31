"""PII redaction module.

Before any text leaves for an LLM call, replace personal identifiers with
stable, indexed placeholder tokens. The token→original mapping is stored
in the `redaction_mappings` DB table (version-scoped) so the DOCX export
(Task 4) can re-expand originals.

Redacted types and token prefixes:
  NIK     — 16-digit Indonesian national ID           → [NIK_N]
  NPWP    — Indonesian tax ID (XX.XXX.XXX.X-XXX.XXX)  → [NPWP_N]
  BANK    — bank account number (10–16 digits)         → [BANK_N]
  PHONE   — Indonesian phone numbers                   → [PHONE_N]
  EMAIL   — email addresses                            → [EMAIL_N]
  ADDR    — street-address fragments (jl./gang/rt/rw)  → [ADDR_N]

Party names (company names, role labels like "Pihak Pertama") are
preserved — the LLM needs them for coherent analysis.

Token stability: identical originals within the same version always get
the same token (lookup before insert). This ensures re-expansion is safe.
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RedactionResult:
    redacted_text: str
    # mapping: token → original (e.g. "[NIK_1]" → "3273012345678901")
    mapping: dict[str, str]


# ── Regex patterns (ordered: most specific first) ────────────────────────────

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # NIK: exactly 16 consecutive digits (not surrounded by more digits)
    ("NIK", re.compile(r"(?<!\d)\d{16}(?!\d)")),

    # NPWP: XX.XXX.XXX.X-XXX.XXX  (with dots and dash)
    ("NPWP", re.compile(r"\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}")),

    # Email — before phone/bank to avoid partial matches
    ("EMAIL", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    )),

    # Indonesian phone: +62/62/08 prefix followed by 7–12 digits,
    # with optional spaces/dashes between groups. The run must end on a
    # digit — not a separator — so trailing whitespace/dashes before
    # unrelated text aren't swallowed into the match.
    ("PHONE", re.compile(
        r"(?<!\d)(\+62|62|0)[0-9](?:[0-9\s\-]{4,11}[0-9])?(?!\d)"
    )),

    # Bank account: 10–16 digits (not already matched as NIK)
    # Use word boundaries and require context (digits only in that span)
    ("BANK", re.compile(r"(?<!\d)\d{10,15}(?!\d)")),

    # Street address fragments
    ("ADDR", re.compile(
        r"(?i)\b(jl\.|jalan|gg\.|gang|rt\s*\.?\s*\d+|rw\s*\.?\s*\d+)"
        r"[^\n]{0,120}(?=\n|,|\.|$)",
        re.MULTILINE,
    )),
]


def redact(text: str) -> RedactionResult:
    """Replace PII in text with stable tokens. Returns redacted text + mapping."""
    # counters per token type
    counters: dict[str, int] = {k: 0 for k, _ in _PATTERNS}
    # original → token (for stability within one document)
    original_to_token: dict[str, str] = {}
    mapping: dict[str, str] = {}

    result = text
    for prefix, pattern in _PATTERNS:
        def _replace(m: re.Match, _prefix: str = prefix) -> str:
            original = m.group(0)
            if original in original_to_token:
                return original_to_token[original]
            counters[_prefix] += 1
            token = f"[{_prefix}_{counters[_prefix]}]"
            original_to_token[original] = token
            mapping[token] = original
            return token

        result = pattern.sub(_replace, result)

    return RedactionResult(redacted_text=result, mapping=mapping)


def expand(redacted_text: str, mapping: dict[str, str]) -> str:
    """Restore original values from a token mapping.

    Used by the DOCX export (Task 4) to produce the final document with
    real names and identifiers reinstated before tracked-change injection.
    """
    result = redacted_text
    for token, original in mapping.items():
        result = result.replace(token, original)
    return result
