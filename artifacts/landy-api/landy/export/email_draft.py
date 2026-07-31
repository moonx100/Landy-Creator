"""Generate a plain-language Bahasa Indonesia negotiation email draft.

Spec §8b: professional, non-adversarial tone; covers material asks; no send
button; includes disclaimer. The LLM is called with the critical/high/medium
risk flags and their negotiation_ask text.
"""
from __future__ import annotations

import sqlalchemy as sa

from landy.database import engine
from landy.llm import LLMError, extract_json, get_llm_client
from landy.logging_setup import logger
from landy.redaction import expand, fetch_mapping, persist_mapping, redact

_DISCLAIMER_FOOTER = """

---
*Catatan: Email ini adalah panduan negosiasi berdasarkan analisis otomatis oleh LANDY Creator. Konten ini merupakan informasi hukum, bukan nasihat hukum, dan bukan pengganti konsultasi dengan advokat. Konsultasikan dengan advokat berlisensi sebelum mengambil keputusan hukum penting.*"""

_SYSTEM_PROMPT = """Anda adalah konsultan negosiasi kontrak profesional Indonesia yang membantu seorang kreator konten menyusun email negosiasi kepada pihak brand/agensi.

Peran Anda adalah menyusun draf komunikasi, bukan memberi nasihat hukum. Konten
yang Anda hasilkan adalah informasi hukum dan panduan negosiasi, bukan nasihat
hukum, dan bukan pengganti konsultasi dengan advokat. Jangan menginstruksikan
kreator untuk menandatangani, menolak, atau membatalkan kontrak — tawarkan
bahasa yang bisa mereka gunakan untuk mendiskusikan atau meminta perubahan.

Tugas Anda: berdasarkan temuan risiko yang diberikan, susun email negosiasi yang:
- Profesional dan tidak konfrontatif ("saya ingin mendiskusikan" bukan "saya menolak")
- Dalam Bahasa Indonesia yang baku dan sopan
- Mencakup semua permintaan negosiasi yang diberikan (negotiation_ask)
- Terstruktur dengan baik (pembuka, isi per poin, penutup)
- Realistis — kreator adalah pihak yang lebih lemah, jadi pendekatan konstruktif
- Maksimal 400 kata

Respons berupa JSON: {"email": "teks email lengkap"}"""


def generate_email_draft(
    document_title: str,
    counterparty: str | None,
    flags: list[dict],  # list of {domain, severity, summary, negotiation_ask, finding_type}
    version_id: str | None = None,
) -> str:
    """Generate a Bahasa Indonesia negotiation email draft.

    Args:
        document_title:  Title of the document.
        counterparty:    Name of the brand/agency (may be None). Party/company
                          names are preserved, not redacted — see redaction.py.
        flags:           Risk flags with their negotiation asks.
        version_id:      UUID string of the source document_versions row, used
                          to load/persist the version-scoped redaction mapping
                          so tokens stay consistent with every other call site
                          for this version. Findings should already be free of
                          raw PII (upstream analysis redacts clause text before
                          the LLM sees it) — this is defence in depth, per the
                          project rule that every chat_complete() call site
                          redacts, without exception.

    Returns:
        Complete email draft text (Bahasa Indonesia, plain text).

    Raises:
        LLMError: If the LLM call fails.
    """
    # Filter to actionable flags (those with a negotiation_ask)
    actionable = [
        f for f in flags
        if f.get("negotiation_ask") and f.get("finding_type") != "absent"
        and f.get("severity") in ("critical", "high", "medium")
    ]

    if not actionable:
        # Fallback: use all flags with negotiation_ask
        actionable = [f for f in flags if f.get("negotiation_ask")]

    to_name = counterparty or "Pihak Brand/Agensi"

    redaction_map: dict[str, str] = {}
    if version_id:
        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
            redaction_map = fetch_mapping(conn, version_id)

    def _redact(text: str) -> str:
        result = redact(text, existing_mapping=redaction_map)
        redaction_map.update(result.mapping)
        return result.redacted_text

    document_title = _redact(document_title)

    # Build the user message
    asks_text = ""
    for i, flag in enumerate(actionable[:12], 1):  # cap at 12 items for context
        asks_text += (
            f"\n{i}. [{flag.get('severity', '').upper()}] {_redact(flag.get('summary', ''))}\n"
            f"   Permintaan: {_redact(flag.get('negotiation_ask', ''))}"
        )

    user_msg = (
        f"Dokumen: {document_title}\n"
        f"Kepada: {to_name}\n\n"
        f"Temuan risiko dan permintaan negosiasi:\n{asks_text}\n\n"
        "Susunlah email negosiasi profesional berdasarkan temuan di atas."
    )

    logger.info(
        "email_draft_generating",
        flag_count=len(actionable),
        document_title=document_title,
    )

    llm = get_llm_client()
    try:
        completion = llm.chat_complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=800,
            json_mode=True,
        )
        data = extract_json(completion.content)
        draft = str(data.get("email") or data.get("draft") or "")
        if not draft:
            raise LLMError("Model returned empty email draft")

        # The model occasionally echoes a redaction token verbatim (e.g. if it
        # quotes a clause back); restore the real value so the draft shown to
        # the creator never surfaces a raw [EMAIL_1]-style placeholder.
        draft = expand(draft, redaction_map)

        if version_id and redaction_map:
            with engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
                persist_mapping(conn, version_id, redaction_map)

        logger.info(
            "email_draft_generated",
            flag_count=len(actionable),
            draft_length=len(draft),
        )
        return draft + _DISCLAIMER_FOOTER

    except (ValueError, KeyError) as exc:
        raise LLMError(f"Failed to parse email draft response: {exc}") from exc
