"""LLM-based materiality classification for version diff entries.

For each changed clause pair, calls the LLM with before/after text and
classifies the change as 'material' or 'immaterial' by legal significance.
Writes usage_events rows for every LLM call.

Changes are sent in batches of up to _BATCH_SIZE per call to keep prompts
focused while minimising API round trips.

Design constraints (spec §9):
  - Never silent failure — classification errors are recorded in
    materiality_reason, not swallowed.
  - Findings are always written in Bahasa Indonesia.
"""
from __future__ import annotations

import json
from typing import Optional

import sqlalchemy as sa

from landy.database import engine
from landy.diff.compute import DiffEntry
from landy.llm import LLMError, extract_json, get_llm_client
from landy.logging_setup import logger

_BATCH_SIZE = 5  # max clause pairs per LLM call

_MATERIALITY_SYSTEM_PROMPT = """\
Anda adalah analis hukum kontrak Indonesia yang berpengalaman, mengkhususkan diri dalam perjanjian antara kreator konten (influencer, artis, YouTuber) dan brand/agensi.

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


def _format_batch(entries: list[DiffEntry], start_idx: int = 1) -> str:
    """Format a batch of diff entries for the LLM prompt."""
    lines = []
    for i, entry in enumerate(entries, start_idx):
        kind_label = {
            "added": "Klausul baru ditambahkan",
            "removed": "Klausul dihapus",
            "modified": "Klausul diubah",
        }.get(entry.change_kind, entry.change_kind)

        lines.append(f"\n[{i}] {kind_label}")
        if entry.before_text:
            lines.append(f"Teks sebelumnya:\n{entry.before_text[:600]}")
        if entry.after_text:
            lines.append(f"Teks baru:\n{entry.after_text[:600]}")
    return "\n".join(lines)


def _parse_batch_response(
    content: str, expected_count: int
) -> list[tuple[str, str]]:
    """Parse the LLM's JSON batch response.

    Returns list of (materiality, reason) tuples, one per entry.
    Falls back to immaterial on any parse error.
    """
    try:
        data = extract_json(content)
        # Handle {"changes": [...]} or bare array
        if isinstance(data, list):
            items = data
        else:
            items = data.get("changes") or data.get("items") or data.get("results") or []

        results = []
        for item in items:
            m = str(item.get("materiality", "immaterial")).lower()
            if m not in ("material", "immaterial"):
                m = "immaterial"
            reason = str(
                item.get("materiality_reason")
                or item.get("reason")
                or "Perubahan redaksional"
            )[:500]
            results.append((m, reason))

        # Pad with fallback if shorter than expected
        while len(results) < expected_count:
            results.append(("immaterial", "Klasifikasi tidak tersedia"))

        return results[:expected_count]

    except (ValueError, KeyError, TypeError):
        return [("immaterial", "Klasifikasi tidak tersedia")] * expected_count


def _write_usage_event(
    conn: sa.engine.Connection,
    job_id: str,
    user_id: str,
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> None:
    conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
    conn.execute(
        sa.text(
            "INSERT INTO usage_events "
            "(user_id, job_id, input_tokens, output_tokens, model) "
            "VALUES (:uid, :jid, :it, :ot, :m)"
        ),
        {
            "uid": user_id,
            "jid": job_id,
            "it": input_tokens,
            "ot": output_tokens,
            "m": model,
        },
    )


def classify_materiality(
    entries: list[DiffEntry],
    job_id: str,
    user_id: str,
) -> list[tuple[str, str]]:
    """Classify each DiffEntry as material or immaterial using the LLM.

    Args:
        entries: List of DiffEntry objects from compute_clause_diff().
        job_id:  UUID string of the analysis_jobs row (for usage_events).
        user_id: UUID string of the owning user (for usage_events).

    Returns:
        List of (materiality, materiality_reason) tuples, parallel to entries.
        On LLM failure, returns ("immaterial", "Klasifikasi tidak tersedia")
        for the failed batch — never raises.
    """
    if not entries:
        return []

    llm = get_llm_client()
    results: list[tuple[str, str]] = []

    # Process in batches of _BATCH_SIZE
    for batch_start in range(0, len(entries), _BATCH_SIZE):
        batch = entries[batch_start : batch_start + _BATCH_SIZE]
        batch_text = _format_batch(batch, start_idx=1)

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
            # Non-fatal fallback — persist rows with "classification unavailable"
            results.extend(
                [("immaterial", "Klasifikasi tidak tersedia")] * len(batch)
            )

    return results
