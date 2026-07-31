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

import sqlalchemy as sa


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


_TOKEN_RE = re.compile(r"^\[([A-Z]+)_(\d+)\]$")


def redact(text: str, existing_mapping: Optional[dict[str, str]] = None) -> RedactionResult:
    """Replace PII in text with stable tokens. Returns redacted text + mapping.

    Args:
        text: text to redact.
        existing_mapping: token→original pairs already assigned for this
            document version (e.g. fetched from `redaction_mappings`, or
            accumulated from earlier `redact()` calls in the same job).
            When given, already-known originals reuse their existing token
            instead of being reassigned, and new counters continue from the
            highest existing index per prefix — so tokens stay stable across
            every call site touching the same version.

    The returned mapping includes both the carried-over `existing_mapping`
    entries and any newly discovered tokens.
    """
    # counters per token type
    counters: dict[str, int] = {k: 0 for k, _ in _PATTERNS}
    # original → token (for stability within one document)
    original_to_token: dict[str, str] = {}
    mapping: dict[str, str] = {}

    if existing_mapping:
        for token, original in existing_mapping.items():
            original_to_token[original] = token
            mapping[token] = original
            m = _TOKEN_RE.match(token)
            if m and m.group(1) in counters:
                counters[m.group(1)] = max(counters[m.group(1)], int(m.group(2)))

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


def fetch_mapping(conn: sa.engine.Connection, version_id: str) -> dict[str, str]:
    """Return the token→original mapping already recorded for a version."""
    rows = conn.execute(
        sa.text("SELECT token, original FROM redaction_mappings WHERE version_id = :vid"),
        {"vid": version_id},
    ).fetchall()
    return {r.token: r.original for r in rows}


def persist_mapping(conn: sa.engine.Connection, version_id: str, mapping: dict[str, str]) -> None:
    """Persist token→original pairs for a version. Idempotent (ON CONFLICT DO NOTHING)."""
    for token, original in mapping.items():
        conn.execute(
            sa.text(
                "INSERT INTO redaction_mappings (version_id, token, original) "
                "VALUES (:vid, :tok, :orig) "
                "ON CONFLICT (version_id, token) DO NOTHING"
            ),
            {"vid": version_id, "tok": token, "orig": original},
        )
