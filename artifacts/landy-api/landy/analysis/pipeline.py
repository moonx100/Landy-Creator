"""LLM analysis pipeline — orchestrates per-domain analysis for a document version.

Entry point: `run_analysis(version_id, job_id, user_id, set_stage_fn)`

Pipeline for each job:
  1. Fetch clauses from DB
  2. Build compact document summary (one LLM call)
  3. For each of 18 domains:
     a. Pre-filter clauses by domain keywords
     b. Call LLM with system prompt + summary + clauses
     c. Parse JSON response (retry once on parse failure)
     d. Persist risk_flags, suggested_edits, citations rows
     e. Log usage_events row
  4. Return (domains_ok, domain_errors)

Partial failure: if some domains error, job completes with warning (state=done,
error_message lists failed domains). If ALL domains error, job is 'failed'.

Spec constraints enforced here:
  - Never silent failure — all errors surfaced in error_message
  - statutes.status is never set (we only write citation shell rows)
  - citation_basis always provided, never inferred
  - governing_language and execution_validity called even with no matching clauses
  - Redaction applied to clause text before sending to LLM
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

import sqlalchemy as sa

from landy.database import engine
from landy.llm import LLMError, extract_json, get_llm_client
from landy.logging_setup import logger
from landy.redaction import redact
from landy.analysis.taxonomy import DOMAIN_INDEX, DOMAINS, Domain

_WORKER_TOKEN = "SYSTEM_WORKER"
_MAX_CLAUSE_CHARS_PER_DOMAIN = 6000   # approx 1500 tokens of clause text per call
_MAX_SUMMARY_INPUT_CHARS = 4000       # first portion of document for summary building
_SUMMARY_MAX_TOKENS = 400


# ── DB row types ──────────────────────────────────────────────────────────────

@dataclass
class ClauseRow:
    id: str
    ordinal: int
    heading_path: Optional[str]
    text: str


@dataclass
class DomainResult:
    """Parsed LLM response for one domain."""
    finding_type: str   # present_risky | absent | ambiguous | none
    severity: str
    summary: str
    rationale: str
    negotiation_ask: Optional[str]
    clause_ordinals: list[int]
    suggested_edits: list[dict]  # [{original_text, revised_text, comment}]
    citation_basis: Optional[str]
    input_tokens: int
    output_tokens: int
    model: str


# ── Worker DB helper ──────────────────────────────────────────────────────────

def _wconn():
    """Context manager for a worker transaction (SYSTEM_WORKER RLS bypass)."""
    return engine.begin()


def _set_worker_rls(conn: sa.engine.Connection) -> None:
    conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))


# ── Clause fetching ───────────────────────────────────────────────────────────

def _fetch_clauses(version_id: str) -> list[ClauseRow]:
    """Fetch all clauses for a version, ordered by ordinal."""
    with _wconn() as conn:
        _set_worker_rls(conn)
        rows = conn.execute(
            sa.text(
                "SELECT id, ordinal, heading_path, text "
                "FROM clauses WHERE version_id = :vid ORDER BY ordinal ASC"
            ),
            {"vid": version_id},
        ).fetchall()
    return [ClauseRow(id=str(r.id), ordinal=r.ordinal, heading_path=r.heading_path, text=r.text)
            for r in rows]


def _filter_clauses(clauses: list[ClauseRow], domain: Domain) -> list[ClauseRow]:
    """Return clauses matching any domain keyword (case-insensitive).
    Falls back to ALL clauses if none match (so domain always sees something)."""
    kws = [k.lower() for k in domain.keywords]
    matched = [c for c in clauses if any(kw in c.text.lower() for kw in kws)]
    return matched if matched else clauses


def _format_clauses(clauses: list[ClauseRow], max_chars: int) -> str:
    """Format clauses as a numbered list, truncating at max_chars."""
    parts: list[str] = []
    total = 0
    for c in clauses:
        heading = f" ({c.heading_path})" if c.heading_path else ""
        # Redact PII from clause text before sending to LLM
        redacted_text = redact(c.text).redacted_text
        entry = f"[Klausul {c.ordinal}{heading}]\n{redacted_text}"
        if total + len(entry) > max_chars:
            parts.append(f"... (klausul selanjutnya dipotong untuk menghemat token)")
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts) if parts else "(Tidak ada klausul yang cocok dengan domain ini)"


# ── Document summary ──────────────────────────────────────────────────────────

def _build_summary(clauses: list[ClauseRow]) -> str:
    """Build a compact document summary using the LLM.

    Used as context for each domain call. Falls back to a simple text extract
    if the LLM call fails (never blocks the main analysis).
    """
    if not clauses:
        return "Dokumen tidak memiliki klausul yang dapat diekstrak."

    # Sample the first N chars for the summary
    sample_text = ""
    for c in clauses:
        sample_text += f"[Klausul {c.ordinal}] {c.text}\n"
        if len(sample_text) >= _MAX_SUMMARY_INPUT_CHARS:
            break

    # Redact PII from the sample
    sample_text = redact(sample_text[:_MAX_SUMMARY_INPUT_CHARS]).redacted_text

    system = (
        "Anda adalah asisten yang merangkum kontrak. "
        "Ekstrak ringkasan singkat (~150 kata) dalam Bahasa Indonesia yang mencakup: "
        "pihak-pihak yang terlibat (Pihak Pertama/Kedua), jenis kontrak, durasi, "
        "dan nilai kontrak jika disebutkan. Respons berupa JSON: "
        '{"ringkasan": "teks ringkasan satu paragraf"}'
    )
    user = f"Kontrak:\n{sample_text}\n\nBuat ringkasan singkat."
    try:
        llm = get_llm_client()
        result = llm.chat_complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=_SUMMARY_MAX_TOKENS,
            json_mode=True,
        )
        data = extract_json(result.content)
        return data.get("ringkasan") or data.get("summary") or str(data)
    except Exception as exc:
        logger.warning("summary_llm_failed", error=str(exc))
        # Graceful fallback: use raw sample text as summary
        return sample_text[:500]


# ── Domain analysis ───────────────────────────────────────────────────────────

def _call_domain(
    domain: Domain,
    summary: str,
    clauses: list[ClauseRow],
) -> DomainResult:
    """Call LLM for one domain and return a parsed DomainResult.

    Retries once on JSON parse failure. Raises LLMError on hard failure.
    """
    llm = get_llm_client()

    # Build clause context
    relevant = _filter_clauses(clauses, domain) if clauses else []
    if not relevant and domain.always_evaluated:
        clauses_text = (
            "Tidak ada klausul yang secara eksplisit membahas domain ini dalam kontrak. "
            "Evaluasi apakah ketidakhadiran klausul ini sendiri merupakan temuan."
        )
    elif not relevant:
        clauses_text = _format_clauses(clauses, _MAX_CLAUSE_CHARS_PER_DOMAIN)
    else:
        clauses_text = _format_clauses(relevant, _MAX_CLAUSE_CHARS_PER_DOMAIN)

    user_msg = (
        f"Ringkasan Dokumen:\n{summary}\n\n"
        f"Klausul-Klausul yang Relevan dengan Domain '{domain.name}':\n{clauses_text}\n\n"
        f"Analisis kontrak ini untuk domain: {domain.name} (key: {domain.key})"
    )

    messages = [
        {"role": "system", "content": domain.system_prompt},
        {"role": "user", "content": user_msg},
    ]

    last_exc: Exception | None = None
    for attempt in range(2):  # try once, retry once on parse failure
        try:
            completion = llm.chat_complete(messages, max_tokens=1500, json_mode=True)
            raw = extract_json(completion.content)
            return _parse_domain_result(raw, completion)
        except (ValueError, KeyError) as exc:
            last_exc = exc
            logger.warning(
                "domain_json_parse_failed",
                domain=domain.key,
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt == 0:
                # Amend the user message asking for correct JSON
                messages.append({"role": "assistant", "content": completion.content})
                messages.append({
                    "role": "user",
                    "content": (
                        "Respons Anda bukan JSON valid. Tolong ulangi HANYA dengan JSON "
                        "sesuai schema yang diminta, tanpa teks tambahan."
                    ),
                })
        except LLMError:
            raise  # hard fail — propagate immediately

    raise LLMError(f"JSON parse failed after 2 attempts for domain {domain.key}: {last_exc}")


def _parse_domain_result(raw: dict, completion) -> DomainResult:
    """Parse a raw LLM JSON response into a DomainResult. Validates fields."""
    VALID_FINDING_TYPES = {"present_risky", "absent", "ambiguous", "none"}
    VALID_SEVERITIES = {"critical", "high", "medium", "info"}

    finding_type = str(raw.get("finding_type", "none")).lower()
    if finding_type not in VALID_FINDING_TYPES:
        finding_type = "none"

    severity = str(raw.get("severity", "info")).lower()
    if severity not in VALID_SEVERITIES:
        severity = "info"

    # Ensure suggested_edits have required fields
    raw_edits = raw.get("suggested_edits") or []
    edits: list[dict] = []
    for e in raw_edits:
        if isinstance(e, dict) and e.get("original_text") and e.get("revised_text"):
            edits.append({
                "original_text": str(e["original_text"]),
                "revised_text": str(e["revised_text"]),
                "comment": str(e.get("comment") or ""),
            })

    # citation_basis — only statutory or doctrinal; never inferred
    raw_basis = raw.get("citation_basis")
    citation_basis = raw_basis if raw_basis in ("statutory", "doctrinal") else None

    return DomainResult(
        finding_type=finding_type,
        severity=severity,
        summary=str(raw.get("summary") or ""),
        rationale=str(raw.get("rationale") or ""),
        negotiation_ask=raw.get("negotiation_ask") or None,
        clause_ordinals=[int(x) for x in (raw.get("clause_ordinals") or []) if str(x).isdigit()],
        suggested_edits=edits,
        citation_basis=citation_basis,
        input_tokens=getattr(completion, "input_tokens", 0),
        output_tokens=getattr(completion, "output_tokens", 0),
        model=getattr(completion, "model", ""),
    )


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist_domain_result(
    domain: Domain,
    result: DomainResult,
    clauses: list[ClauseRow],
    version_id: str,
    job_id: str,
    user_id: str,
) -> None:
    """Write risk_flag, suggested_edits, citation, and usage_event rows.

    risk_flags carries job_id (migration 0006) so results endpoint can return
    exactly one run's findings regardless of how many times the version is reanalysed.
    usage_events is written for every LLM call including finding_type='none'.
    """
    # Map ordinal → clause UUID
    ordinal_map = {c.ordinal: c.id for c in clauses}

    # Resolve primary clause_id (first ordinal that exists in DB)
    clause_id: str | None = None
    for ord_ in result.clause_ordinals:
        if ord_ in ordinal_map:
            clause_id = ordinal_map[ord_]
            break

    with _wconn() as conn:
        _set_worker_rls(conn)

        if result.finding_type != "none":
            # Insert risk_flag — job_id scopes it to this specific run
            flag_row = conn.execute(
                sa.text(
                    "INSERT INTO risk_flags "
                    "(job_id, clause_id, version_id, domain, severity, finding_type, "
                    " summary, rationale, negotiation_ask) "
                    "VALUES (:jid, :cid, :vid, :domain, :severity, :ftype, "
                    "        :summary, :rationale, :nask) "
                    "RETURNING id"
                ),
                {
                    "jid": job_id,
                    "cid": clause_id,
                    "vid": version_id,
                    "domain": domain.key,
                    "severity": result.severity,
                    "ftype": result.finding_type,
                    "summary": result.summary[:1000],
                    "rationale": result.rationale[:4000],
                    "nask": result.negotiation_ask[:2000] if result.negotiation_ask else None,
                },
            ).fetchone()
            flag_id = str(flag_row.id)

            # Insert suggested_edits
            for edit in result.suggested_edits:
                conn.execute(
                    sa.text(
                        "INSERT INTO suggested_edits "
                        "(risk_flag_id, clause_id, original_text, revised_text, comment) "
                        "VALUES (:fid, :cid, :orig, :rev, :comment)"
                    ),
                    {
                        "fid": flag_id,
                        "cid": clause_id,
                        "orig": edit["original_text"][:4000],
                        "rev": edit["revised_text"][:4000],
                        "comment": edit["comment"][:1000],
                    },
                )

            # Insert citation placeholder (shell row, provision_id=NULL per spec)
            # statutes.status is NEVER set by code — operator only
            if result.citation_basis:
                conn.execute(
                    sa.text(
                        "INSERT INTO citations "
                        "(risk_flag_id, provision_id, citation_text, basis) "
                        "VALUES (:fid, NULL, NULL, :basis)"
                    ),
                    {"fid": flag_id, "basis": result.citation_basis},
                )

            logger.info(
                "domain_result_persisted",
                domain=domain.key,
                finding_type=result.finding_type,
                severity=result.severity,
                flag_id=flag_id,
                edits=len(result.suggested_edits),
            )

        # Always write usage_events — every LLM call counts toward metering,
        # even when finding_type='none'. Store zeros explicitly when provider
        # omits usage metadata (some compatible endpoints do this).
        conn.execute(
            sa.text(
                "INSERT INTO usage_events "
                "(user_id, job_id, input_tokens, output_tokens, model) "
                "VALUES (:uid, :jid, :inp, :out, :model)"
            ),
            {
                "uid": user_id,
                "jid": job_id,
                "inp": result.input_tokens,   # 0 if provider omitted usage
                "out": result.output_tokens,  # 0 if provider omitted usage
                "model": result.model[:100] if result.model else "",
            },
        )


# ── Public entry point ────────────────────────────────────────────────────────

def run_analysis(
    version_id: str,
    job_id: str,
    user_id: str,
    set_stage_fn: Callable[[str], None],
) -> tuple[int, list[str]]:
    """Run the full 18-domain LLM analysis for one document version.

    Args:
        version_id:    UUID string of the document_versions row.
        job_id:        UUID string of the analysis_jobs row.
        user_id:       UUID string of the owning user (for usage_events).
        set_stage_fn:  Callback to update analysis_jobs.stage in the worker.

    Returns:
        (domains_ok, domain_errors) — count of successful domains and list of
        error strings for failed domains.

    Raises:
        LLMError: If the LLM client cannot be initialised (bad config).
                  Propagated so the worker can mark the job as 'failed'.
    """
    # Validate LLM client early — fail fast before doing any work
    llm = get_llm_client()

    set_stage_fn("Memuat klausul dari database")
    clauses = _fetch_clauses(version_id)

    if not clauses:
        logger.warning("analysis_no_clauses", version_id=version_id)
        # Still run all 18 domains; the always-evaluated ones will get 'absent' findings

    set_stage_fn("Membangun ringkasan dokumen")
    summary = _build_summary(clauses)
    logger.info("summary_built", version_id=version_id, length=len(summary))

    domains_ok = 0
    domain_errors: list[str] = []

    for domain in DOMAINS:
        stage_label = f"Menganalisis domain: {domain.name}"
        set_stage_fn(stage_label)
        logger.info("domain_analysis_start", domain=domain.key, version_id=version_id)

        try:
            result = _call_domain(domain, summary, clauses)
            _persist_domain_result(domain, result, clauses, version_id, job_id, user_id)
            domains_ok += 1
            logger.info(
                "domain_analysis_done",
                domain=domain.key,
                finding_type=result.finding_type,
                in_tokens=result.input_tokens,
                out_tokens=result.output_tokens,
            )
        except LLMError as exc:
            err = f"{domain.key}: {exc}"
            domain_errors.append(err)
            logger.error("domain_analysis_failed", domain=domain.key, error=str(exc))
        except Exception as exc:
            err = f"{domain.key}: unexpected error — {exc}"
            domain_errors.append(err)
            logger.error("domain_analysis_unexpected", domain=domain.key, error=str(exc))

    return domains_ok, domain_errors
