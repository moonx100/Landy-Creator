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
  - Redaction applied to summary sample text, clause text, and comment
    bubbles before any of it reaches the LLM (shared, version-scoped mapping)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

import sqlalchemy as sa

from landy.database import engine
from landy.llm import LLMError, extract_json, get_llm_client
from landy.logging_setup import logger
from landy.redaction import fetch_mapping, persist_mapping, redact
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


def _fetch_comments(version_id: str) -> list[dict]:
    """Fetch document comment bubbles for a version, ordered by ordinal.

    Returns an empty list when no comments exist (PDF, no bubbles, or parse
    failure during extraction — all of which set no rows in document_comments).
    """
    with _wconn() as conn:
        _set_worker_rls(conn)
        rows = conn.execute(
            sa.text(
                "SELECT author, comment_date, anchor_text, body, ordinal "
                "FROM document_comments "
                "WHERE version_id = :vid "
                "ORDER BY ordinal ASC"
            ),
            {"vid": version_id},
        ).fetchall()
    return [
        {
            "author": r.author,
            "anchor_text": r.anchor_text,
            "body": r.body,
        }
        for r in rows
    ]


def _filter_clauses(clauses: list[ClauseRow], domain: Domain) -> list[ClauseRow]:
    """Return clauses matching any domain keyword (case-insensitive).
    Falls back to ALL clauses if none match (so domain always sees something)."""
    kws = [k.lower() for k in domain.keywords]
    matched = [c for c in clauses if any(kw in c.text.lower() for kw in kws)]
    return matched if matched else clauses


def _format_clauses(clauses: list[ClauseRow], max_chars: int, redaction_map: dict[str, str]) -> str:
    """Format clauses as a numbered list, truncating at max_chars.

    redaction_map is the version-scoped token→original mapping, mutated in
    place so tokens stay stable with every other call site for this version.
    """
    parts: list[str] = []
    total = 0
    for c in clauses:
        heading = f" ({c.heading_path})" if c.heading_path else ""
        # Redact PII from clause text before sending to LLM
        redaction_result = redact(c.text, existing_mapping=redaction_map)
        redaction_map.update(redaction_result.mapping)
        redacted_text = redaction_result.redacted_text
        entry = f"[Klausul {c.ordinal}{heading}]\n{redacted_text}"
        if total + len(entry) > max_chars:
            parts.append(f"... (klausul selanjutnya dipotong untuk menghemat token)")
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts) if parts else "(Tidak ada klausul yang cocok dengan domain ini)"


# ── Document summary ──────────────────────────────────────────────────────────

def _build_summary(
    clauses: list[ClauseRow], redaction_map: dict[str, str]
) -> tuple[Optional[str], str]:
    """Build a compact document summary using the LLM.

    Returns (summary_text, status) where status is 'ok' or 'failed'. On
    failure the summary is None — never a raw text slice masquerading as a
    summary (LC-35). Domain prompts omit the summary section instead, and
    the failure is recorded on analysis_jobs.summary_status.

    redaction_map is the version-scoped token→original mapping, mutated in
    place so tokens stay stable with every other call site for this version.
    """
    if not clauses:
        return "Dokumen tidak memiliki klausul yang dapat diekstrak.", "ok"

    # Sample the first N chars for the summary
    sample_text = ""
    for c in clauses:
        sample_text += f"[Klausul {c.ordinal}] {c.text}\n"
        if len(sample_text) >= _MAX_SUMMARY_INPUT_CHARS:
            break

    # Redact PII from the sample
    redaction_result = redact(sample_text[:_MAX_SUMMARY_INPUT_CHARS], existing_mapping=redaction_map)
    redaction_map.update(redaction_result.mapping)
    sample_text = redaction_result.redacted_text

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
        return (data.get("ringkasan") or data.get("summary") or str(data)), "ok"
    except Exception as exc:
        logger.warning("summary_llm_failed", error=str(exc))
        # No fallback value: a failed summary is a recorded failure, never a
        # raw text slice presented as analysis (LC-35).
        return None, "failed"


# ── Metering ──────────────────────────────────────────────────────────────────

def _write_usage_event(
    job_id: str,
    user_id: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    model: Optional[str],
    status: str = "ok",
    failure_stage: Optional[str] = None,
) -> None:
    """Insert one usage row per provider round-trip.

    Failed calls carry NULL tokens (never a local estimate); billed calls
    whose result was later discarded keep their real counts with
    status='failed' (LC-36/LC-37).
    """
    with _wconn() as conn:
        _set_worker_rls(conn)
        conn.execute(
            sa.text(
                "INSERT INTO usage_events "
                "(user_id, job_id, input_tokens, output_tokens, model, status, failure_stage) "
                "VALUES (:uid, :jid, :inp, :out, :model, :st, :fs)"
            ),
            {
                "uid": user_id,
                "jid": job_id,
                "inp": input_tokens,
                "out": output_tokens,
                "model": (model[:100] if model else None),
                "st": status,
                "fs": failure_stage,
            },
        )


def _record_domain_run(
    job_id: str, domain_key: str, status: str, error: Optional[str] = None
) -> None:
    """Record the outcome of one domain attempt (LC-41).

    One row per (job, domain), idempotent on re-run. 'No risk flags' for a
    job is only derivable from a complete set of 'ok' rows.
    """
    with _wconn() as conn:
        _set_worker_rls(conn)
        conn.execute(
            sa.text(
                "INSERT INTO analysis_domain_runs (job_id, domain_key, status, error) "
                "VALUES (:jid, :dk, :st, :err) "
                "ON CONFLICT (job_id, domain_key) DO UPDATE "
                "SET status = EXCLUDED.status, error = EXCLUDED.error, "
                "    created_at = now()"
            ),
            {"jid": job_id, "dk": domain_key, "st": status, "err": (error or None)},
        )


def _fetch_carryover_domains(version_id: str, current_job_id: str) -> dict[str, str]:
    """Return {domain_key: prior_job_id} for domains that succeeded in the
    most recent FAILED job for this version.

    MV decision 2026-08-02: a retry after a majority-failed job re-runs only
    the failed checks — successful results are carried forward, never paid
    for twice. Carry-over applies only when the latest prior job failed; a
    fresh analysis of a previously completed version is deliberate and runs
    in full.
    """
    with _wconn() as conn:
        _set_worker_rls(conn)
        prior = conn.execute(
            sa.text(
                "SELECT id, state FROM analysis_jobs "
                "WHERE version_id = :vid AND id != :jid "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"vid": version_id, "jid": current_job_id},
        ).fetchone()
        if not prior or prior.state != "failed":
            return {}
        rows = conn.execute(
            sa.text(
                "SELECT domain_key FROM analysis_domain_runs "
                "WHERE job_id = :jid AND status = 'ok'"
            ),
            {"jid": str(prior.id)},
        ).fetchall()
    return {r.domain_key: str(prior.id) for r in rows}


def _carry_forward_domain(old_job_id: str, new_job_id: str, domain_key: str) -> None:
    """Copy one domain's persisted findings from a prior job to this job."""
    with _wconn() as conn:
        _set_worker_rls(conn)
        old_flags = conn.execute(
            sa.text(
                "SELECT id, clause_id, version_id, domain, severity, finding_type, "
                "summary, rationale, negotiation_ask "
                "FROM risk_flags WHERE job_id = :jid AND domain = :dk"
            ),
            {"jid": old_job_id, "dk": domain_key},
        ).fetchall()
        for f in old_flags:
            new_flag = conn.execute(
                sa.text(
                    "INSERT INTO risk_flags "
                    "(job_id, clause_id, version_id, domain, severity, finding_type, "
                    " summary, rationale, negotiation_ask) "
                    "VALUES (:jid, :cid, :vid, :domain, :sev, :ftype, :summary, :rat, :nask) "
                    "RETURNING id"
                ),
                {
                    "jid": new_job_id,
                    "cid": f.clause_id,
                    "vid": f.version_id,
                    "domain": f.domain,
                    "sev": f.severity,
                    "ftype": f.finding_type,
                    "summary": f.summary,
                    "rat": f.rationale,
                    "nask": f.negotiation_ask,
                },
            ).fetchone()
            conn.execute(
                sa.text(
                    "INSERT INTO suggested_edits "
                    "(risk_flag_id, clause_id, original_text, revised_text, comment) "
                    "SELECT :new_fid, clause_id, original_text, revised_text, comment "
                    "FROM suggested_edits WHERE risk_flag_id = :old_fid"
                ),
                {"new_fid": str(new_flag.id), "old_fid": str(f.id)},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO citations "
                    "(risk_flag_id, provision_id, citation_text, basis) "
                    "SELECT :new_fid, provision_id, citation_text, basis "
                    "FROM citations WHERE risk_flag_id = :old_fid"
                ),
                {"new_fid": str(new_flag.id), "old_fid": str(f.id)},
            )


# ── Domain analysis ───────────────────────────────────────────────────────────

def _format_comments(comments: list[dict], redaction_map: dict[str, str], max_comments: int = 20) -> str:
    """Format extracted document comments for inclusion in the LLM prompt.

    Comment author/body/anchor text can carry PII (a reviewer's name, an
    email, a phone number quoted in a note) just like clause text, so it is
    redacted the same way before it reaches the LLM. redaction_map is the
    version-scoped token→original mapping, mutated in place so tokens stay
    stable with every other call site for this version.
    """
    if not comments:
        return ""
    lines: list[str] = []
    for c in comments[:max_comments]:
        author = c.get("author")
        if author:
            author_result = redact(author, existing_mapping=redaction_map)
            redaction_map.update(author_result.mapping)
            author_label = f"[{author_result.redacted_text}]"
        else:
            author_label = "[Tanpa nama]"

        body_result = redact(c.get("body") or "", existing_mapping=redaction_map)
        redaction_map.update(body_result.mapping)
        body = body_result.redacted_text

        anchor = ""
        if c.get("anchor_text"):
            anchor_result = redact(c["anchor_text"][:120], existing_mapping=redaction_map)
            redaction_map.update(anchor_result.mapping)
            anchor = f" (terkait teks: \"{anchor_result.redacted_text}\")"

        lines.append(f"- {author_label}: {body}{anchor}")
    return "\n".join(lines)


def _call_domain(
    domain: Domain,
    summary: Optional[str],
    clauses: list[ClauseRow],
    redaction_map: dict[str, str],
    job_id: str,
    user_id: str,
    comments: list[dict] | None = None,
) -> DomainResult:
    """Call LLM for one domain and return a parsed DomainResult.

    Retries once on JSON parse failure. Raises LLMError on hard failure.

    Metering (LC-36/LC-37): every provider round-trip writes its own
    usage_events row at the point it happens — a billed completion whose JSON
    could not be parsed is recorded with its real token counts and
    status='failed' before the error propagates; a call that never returned
    is recorded with NULL tokens.
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
        clauses_text = _format_clauses(clauses, _MAX_CLAUSE_CHARS_PER_DOMAIN, redaction_map)
    else:
        clauses_text = _format_clauses(relevant, _MAX_CLAUSE_CHARS_PER_DOMAIN, redaction_map)

    # A failed summary is omitted, never substituted with raw text (LC-35).
    if summary:
        user_msg = f"Ringkasan Dokumen:\n{summary}\n\n"
    else:
        user_msg = (
            "Ringkasan dokumen tidak tersedia untuk analisis ini — "
            "gunakan klausul di bawah sebagai satu-satunya konteks.\n\n"
        )
    user_msg += (
        f"Klausul-Klausul yang Relevan dengan Domain '{domain.name}':\n{clauses_text}\n\n"
    )

    # Include comment bubbles so the LLM can flag concerns raised in comments
    if comments:
        comment_text = _format_comments(comments, redaction_map)
        user_msg += (
            f"Komentar yang Ditambahkan oleh Pihak Lain dalam Dokumen:\n"
            f"{comment_text}\n\n"
        )

    user_msg += f"Analisis kontrak ini untuk domain: {domain.name} (key: {domain.key})"

    messages = [
        {"role": "system", "content": domain.system_prompt},
        {"role": "user", "content": user_msg},
    ]

    last_exc: Exception | None = None
    for attempt in range(2):  # try once, retry once on parse failure
        try:
            completion = llm.chat_complete(messages, max_tokens=1500, json_mode=True)
        except LLMError:
            # No completion exists — meter the failed attempt with NULL
            # tokens (no local estimates) and propagate (LC-36).
            _write_usage_event(
                job_id, user_id, None, None, None,
                status="failed", failure_stage=f"llm_call:{domain.key}",
            )
            raise  # hard fail — propagate immediately

        try:
            raw = extract_json(completion.content)
            result = _parse_domain_result(raw, completion)
        except (ValueError, KeyError) as exc:
            # The provider billed this round-trip; its real token counts are
            # persisted before anything else happens to them (LC-37).
            _write_usage_event(
                job_id, user_id,
                getattr(completion, "input_tokens", 0),
                getattr(completion, "output_tokens", 0),
                getattr(completion, "model", ""),
                status="failed", failure_stage=f"json_parse:{domain.key}",
            )
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
            continue

        # Success — meter this round-trip here, at the point it happened.
        _write_usage_event(
            job_id, user_id,
            result.input_tokens, result.output_tokens, result.model,
            status="ok",
        )
        return result

    raise LLMError(f"JSON parse failed after 2 attempts for domain {domain.key}: {last_exc}")


def _parse_domain_result(raw: dict, completion) -> DomainResult:
    """Parse a raw LLM JSON response into a DomainResult. Validates fields.

    An out-of-vocabulary finding_type or severity is a parse failure
    (ValueError → retry → domain run 'failed'), never a coercion: coercing
    finding_type to 'none' erased genuine findings, and coercing severity to
    'info' demoted them to the quietest badge (LC-34, LC-30/LC-41).
    """
    VALID_FINDING_TYPES = {"present_risky", "absent", "ambiguous", "none"}
    VALID_SEVERITIES = {"critical", "high", "medium", "info"}

    finding_type = str(raw.get("finding_type", "")).lower()
    if finding_type not in VALID_FINDING_TYPES:
        raise ValueError(f"finding_type di luar vokabulari: {finding_type!r}")

    severity = str(raw.get("severity", "")).lower()
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"severity di luar vokabulari: {severity!r}")

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

        # Metering note: usage_events are written per provider round-trip in
        # _call_domain (including failed attempts) — not here, to avoid
        # double-counting and to keep failed calls meterable (LC-36/LC-37).


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

    # Fetch comment bubbles — empty list for PDFs / no-comment documents
    comments = _fetch_comments(version_id)
    if comments:
        logger.info(
            "analysis_comments_loaded",
            version_id=version_id,
            count=len(comments),
        )

    # Load the version-scoped redaction mapping (populated by the worker's
    # document-level redact() pass) so every LLM call site for this version
    # — summary, clauses, comments — reuses the same tokens instead of each
    # deriving its own local numbering.
    with _wconn() as conn:
        _set_worker_rls(conn)
        redaction_map = fetch_mapping(conn, version_id)

    set_stage_fn("Membangun ringkasan dokumen")
    summary, summary_status = _build_summary(clauses, redaction_map)
    logger.info(
        "summary_built",
        version_id=version_id,
        status=summary_status,
        length=len(summary) if summary else 0,
    )
    # Record the summary outcome on the job — a failed summary is visible,
    # never silently replaced (LC-35).
    with _wconn() as conn:
        _set_worker_rls(conn)
        conn.execute(
            sa.text("UPDATE analysis_jobs SET summary_status = :st WHERE id = :jid"),
            {"st": summary_status, "jid": job_id},
        )

    domains_ok = 0
    domain_errors: list[str] = []

    # Retry-only-failed: carry forward successful results from the most
    # recent failed job for this version (MV decision 2026-08-02).
    carryover = _fetch_carryover_domains(version_id, job_id)
    if carryover:
        logger.info(
            "analysis_carryover",
            job_id=job_id,
            version_id=version_id,
            carried_domains=sorted(carryover.keys()),
        )

    for domain in DOMAINS:
        if domain.key in carryover:
            _carry_forward_domain(carryover[domain.key], job_id, domain.key)
            _record_domain_run(job_id, domain.key, "ok")
            domains_ok += 1
            logger.info("domain_carried_forward", domain=domain.key, job_id=job_id)
            continue

        stage_label = f"Menganalisis domain: {domain.name}"
        set_stage_fn(stage_label)
        logger.info("domain_analysis_start", domain=domain.key, version_id=version_id)

        try:
            result = _call_domain(
                domain, summary, clauses, redaction_map, job_id, user_id,
                comments=comments,
            )
            _persist_domain_result(domain, result, clauses, version_id, job_id, user_id)
            _record_domain_run(job_id, domain.key, "ok")
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
            _record_domain_run(job_id, domain.key, "failed", str(exc))
            logger.error("domain_analysis_failed", domain=domain.key, error=str(exc))
        except Exception as exc:
            err = f"{domain.key}: unexpected error — {exc}"
            domain_errors.append(err)
            _record_domain_run(job_id, domain.key, "failed", str(exc))
            logger.error("domain_analysis_unexpected", domain=domain.key, error=str(exc))

    # Persist any new tokens discovered while formatting summary/clauses/comments
    # (e.g. PII in a comment bubble that wasn't in the document body redaction).
    with _wconn() as conn:
        _set_worker_rls(conn)
        persist_mapping(conn, version_id, redaction_map)

    return domains_ok, domain_errors
