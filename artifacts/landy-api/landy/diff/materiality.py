"""LLM-based materiality classification for version diff entries.

For each changed clause pair, calls the LLM with before/after text and
classifies the change as 'material' or 'immaterial' by legal significance.
Writes usage_events rows for every LLM call.

Changes are sent in batches of up to _BATCH_SIZE per call to keep prompts
focused while minimising API round trips.

Design constraints (spec §9 + LC-41, decided 2026-08-02):
  - Never silent failure — a change the model could not classify is returned
    with status='failed' and materiality=None, never as a fabricated
    'immaterial'. The DB CHECK (version_diffs_materiality_state) makes the
    dishonest combination unrepresentable.
  - Every LLM attempt writes a usage_events row, including failures
    (status='failed', NULL tokens — no local estimates).
  - Findings are always written in Bahasa Indonesia.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa

from landy.database import engine
from landy.diff.compute import DiffEntry
from landy.llm import LLMError, extract_json, get_llm_client
from landy.logging_setup import logger
from landy.redaction import fetch_mapping, persist_mapping, redact

_BATCH_SIZE = 5  # max clause pairs per LLM call


@dataclass
class MaterialityResult:
    """Outcome of classifying one diff entry.

    The semantic answer (materiality) and the operational outcome (status)
    are separate facts: status='failed' always carries materiality=None —
    the absence of an answer is never rendered as a negative answer.
    """
    materiality: Optional[str]   # 'material' | 'immaterial' | None when failed
    status: str                  # 'ok' | 'failed' ('low_confidence' reserved)
    reason: Optional[str]        # LLM rationale when ok; error detail when failed


def _failed(reason: str) -> MaterialityResult:
    return MaterialityResult(materiality=None, status="failed", reason=reason)

_MATERIALITY_SYSTEM_PROMPT = """\
Anda adalah analis hukum kontrak Indonesia yang berpengalaman, mengkhususkan diri dalam perjanjian antara kreator konten (influencer, artis, YouTuber) dan brand/agensi.

Klasifikasi yang Anda hasilkan adalah informasi hukum untuk membantu kreator memahami perubahan kontrak, bukan nasihat hukum, dan bukan pengganti konsultasi dengan advokat. Jangan menyimpulkan bahwa kreator harus menandatangani, menolak, atau membatalkan kontrak — cukup jelaskan sifat perubahannya.

Tugas Anda: Untuk setiap perubahan klausul yang diberikan, tentukan apakah perubahan tersebut MATERIAL atau TIDAK MATERIAL dari sudut pandang hukum yang mempengaruhi posisi kreator.

Perubahan MATERIAL: perubahan yang secara nyata menggeser posisi hukum kreator, contohnya:
- Mengubah cakupan pemberian hak (IP, penggunaan, eksklusivitas, media whitelisting)
- Mengubah kewajiban atau jadwal pembayaran
- Mengubah jangka waktu kontrak, syarat perpanjangan, atau syarat pemutusan
- Menambah atau menghapus klausul ganti rugi (indemnifikasi) atau batas kewajiban
- Mengubah hak moral kreator (inalienable menurut UU Hak Cipta Indonesia)
- Mengubah forum atau hukum penyelesaian sengketa
- Menambah atau memperluas larangan kompetisi pasca-kontrak
- Mengubah syarat kerahasiaan secara substantif
- Mengubah klausul moralitas atau kondisi pemutusan sepihak

Perubahan TIDAK MATERIAL: perubahan yang tidak mengubah posisi hukum secara substantif, contohnya:
- Perubahan redaksional, penyempurnaan bahasa, atau perbaikan gaya
- Perubahan format, penomoran pasal, atau referensi silang
- Koreksi ejaan, tanda baca, atau konsistensi istilah tanpa perubahan makna
- Klarifikasi yang tidak mengubah hak atau kewajiban secara substantif

Kembalikan JSON object dengan format:
{"changes": [{"index": 1, "materiality": "material" atau "immaterial", "materiality_reason": "Satu kalimat singkat dalam Bahasa Indonesia menjelaskan alasannya"}, ...]}
"""


def _format_batch(
    entries: list[DiffEntry], redaction_map: dict[str, str], start_idx: int = 1
) -> str:
    """Format a batch of diff entries for the LLM prompt.

    The diff itself (DiffEntry.before_text/after_text) intentionally stays
    non-redacted for display — see diff/compute.py. Only the copy sent to the
    LLM here is redacted, reusing the version-scoped mapping so tokens stay
    consistent with every other call site for this version. redaction_map is
    mutated in place with any newly discovered tokens.
    """
    lines = []
    for i, entry in enumerate(entries, start_idx):
        kind_label = {
            "added": "Klausul baru ditambahkan",
            "removed": "Klausul dihapus",
            "modified": "Klausul diubah",
        }.get(entry.change_kind, entry.change_kind)

        lines.append(f"\n[{i}] {kind_label}")
        if entry.before_text:
            before_result = redact(entry.before_text[:600], existing_mapping=redaction_map)
            redaction_map.update(before_result.mapping)
            lines.append(f"Teks sebelumnya:\n{before_result.redacted_text}")
        if entry.after_text:
            after_result = redact(entry.after_text[:600], existing_mapping=redaction_map)
            redaction_map.update(after_result.mapping)
            lines.append(f"Teks baru:\n{after_result.redacted_text}")
    return "\n".join(lines)


def _parse_batch_response(
    content: str, expected_count: int
) -> list[MaterialityResult]:
    """Parse the LLM's JSON batch response.

    Returns one MaterialityResult per expected entry. Any item the model did
    not answer, answered out of vocabulary, or that was lost to a parse error
    comes back as status='failed' with materiality=None — never as a
    fabricated 'immaterial'.
    """
    try:
        data = extract_json(content)
        # Handle {"changes": [...]} or bare array
        if isinstance(data, list):
            items = data
        else:
            items = data.get("changes") or data.get("items") or data.get("results") or []

        results: list[MaterialityResult] = []
        for item in items:
            m = str(item.get("materiality", "")).lower()
            if m not in ("material", "immaterial"):
                # Out-of-vocabulary or missing answer is a failed
                # classification, not a quiet immaterial.
                results.append(_failed(
                    f"Jawaban model di luar vokabulari: {m!r}" if m
                    else "Model tidak memberikan klasifikasi"
                ))
                continue
            reason = str(
                item.get("materiality_reason")
                or item.get("reason")
                or "Tidak ada alasan diberikan"
            )[:500]
            results.append(MaterialityResult(materiality=m, status="ok", reason=reason))

        # Entries the model never answered are failures, not immaterial.
        while len(results) < expected_count:
            results.append(_failed("Respons model tidak lengkap untuk entri ini"))

        return results[:expected_count]

    except (ValueError, KeyError, TypeError) as exc:
        return [
            _failed(f"Respons model tidak dapat diurai: {exc}")
        ] * expected_count


def _write_usage_event(
    conn: sa.engine.Connection,
    job_id: str,
    user_id: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    model: Optional[str],
    status: str = "ok",
    failure_stage: Optional[str] = None,
) -> None:
    """Insert one usage row. Failed calls carry NULL tokens and status='failed' —
    no locally estimated token counts (LC-36)."""
    conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
    conn.execute(
        sa.text(
            "INSERT INTO usage_events "
            "(user_id, job_id, input_tokens, output_tokens, model, status, failure_stage) "
            "VALUES (:uid, :jid, :it, :ot, :m, :st, :fs)"
        ),
        {
            "uid": user_id,
            "jid": job_id,
            "it": input_tokens,
            "ot": output_tokens,
            "m": model,
            "st": status,
            "fs": failure_stage,
        },
    )


def classify_materiality(
    entries: list[DiffEntry],
    job_id: str,
    user_id: str,
    version_id: str,
) -> list[MaterialityResult]:
    """Classify each DiffEntry as material or immaterial using the LLM.

    Args:
        entries:    List of DiffEntry objects from compute_clause_diff().
        job_id:     UUID string of the analysis_jobs row (for usage_events).
        user_id:    UUID string of the owning user (for usage_events).
        version_id: UUID string of the target document_versions row — used to
                    load/persist the version-scoped redaction mapping so
                    clause text sent to the LLM here uses the same tokens as
                    every other call site for this version.

    Returns:
        List of MaterialityResult, parallel to entries. On LLM failure the
        affected batch returns status='failed' with materiality=None — never
        a fabricated value, and never raises. Failed calls still write a
        usage_events row (status='failed', NULL tokens).
    """
    if not entries:
        return []

    llm = get_llm_client()
    results: list[MaterialityResult] = []

    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        redaction_map = fetch_mapping(conn, version_id)

    # Process in batches of _BATCH_SIZE
    for batch_start in range(0, len(entries), _BATCH_SIZE):
        batch = entries[batch_start : batch_start + _BATCH_SIZE]
        batch_text = _format_batch(batch, redaction_map, start_idx=1)

        messages = [
            {"role": "system", "content": _MATERIALITY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Klasifikasikan {len(batch)} perubahan klausul berikut "
                    f"sebagai material atau immaterial:\n{batch_text}\n\n"
                    "Kembalikan JSON dengan key 'changes' berisi array hasil klasifikasi."
                ),
            },
        ]

        try:
            completion = llm.chat_complete(
                messages, max_tokens=600, json_mode=True
            )
            batch_results = _parse_batch_response(completion.content, len(batch))

            with engine.begin() as conn:
                _write_usage_event(
                    conn,
                    job_id,
                    user_id,
                    completion.input_tokens,
                    completion.output_tokens,
                    completion.model,
                )

            logger.info(
                "materiality_batch_done",
                job_id=job_id,
                batch_size=len(batch),
                in_tokens=completion.input_tokens,
                out_tokens=completion.output_tokens,
            )
            results.extend(batch_results)

        except LLMError as exc:
            logger.error(
                "materiality_batch_failed",
                job_id=job_id,
                batch_start=batch_start,
                error=str(exc),
            )
            # Meter the failed attempt — NULL tokens, honest status (LC-36).
            with engine.begin() as conn:
                _write_usage_event(
                    conn, job_id, user_id,
                    input_tokens=None, output_tokens=None, model=None,
                    status="failed", failure_stage="materiality_llm",
                )
            # Non-fatal for the pipeline, but never a fabricated value: the
            # whole batch is returned as failed classifications.
            results.extend(
                [_failed(f"Panggilan LLM gagal: {exc}")] * len(batch)
            )

    # Persist any new tokens discovered while formatting batch text.
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
        persist_mapping(conn, version_id, redaction_map)

    return results
