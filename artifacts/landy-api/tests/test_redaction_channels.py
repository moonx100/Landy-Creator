"""Tests for PII redaction on the diff, comment, and email LLM channels.

Covers the Step 1 privacy-path acceptance: no un-redacted contract text
reaches chat_complete() on the diff path (materiality.py), the comment path
(analysis/pipeline.py _format_comments), or the email path
(export/email_draft.py) — and tokens stay consistent with a version's
existing redaction mapping so export can re-expand them.

Run with:
    python -m pytest tests/test_redaction_channels.py -v
    DATABASE_URL=... python -m pytest tests/test_redaction_channels.py -v  (for the email-draft integration test)
"""
from __future__ import annotations

import os
import uuid

import pytest

from landy.redaction import expand, redact


# ── redact() mapping reuse ──────────────────────────────────────────────────

class TestRedactMappingReuse:
    def test_new_originals_get_fresh_tokens(self):
        result = redact("Hubungi saya di budi@example.com")
        assert "budi@example.com" not in result.redacted_text
        assert "[EMAIL_1]" in result.redacted_text

    def test_existing_mapping_reuses_same_token(self):
        existing = {"[EMAIL_1]": "budi@example.com"}
        result = redact("Email: budi@example.com", existing_mapping=existing)
        assert result.redacted_text == "Email: [EMAIL_1]"
        assert result.mapping["[EMAIL_1]"] == "budi@example.com"

    def test_new_originals_continue_counter_from_existing_mapping(self):
        existing = {"[EMAIL_1]": "already-known@example.com"}
        result = redact("Kontak baru: fresh@example.com", existing_mapping=existing)
        assert "[EMAIL_2]" in result.redacted_text
        assert result.mapping["[EMAIL_2]"] == "fresh@example.com"
        # existing entry carried through
        assert result.mapping["[EMAIL_1]"] == "already-known@example.com"

    def test_expand_restores_originals(self):
        result = redact("NIK saya 3273010101010001")
        restored = expand(result.redacted_text, result.mapping)
        assert restored == "NIK saya 3273010101010001"


# ── Diff path: materiality._format_batch ────────────────────────────────────

class TestMaterialityFormatBatchRedacts:
    def test_pii_in_clause_text_is_redacted(self):
        from landy.diff.compute import DiffEntry
        from landy.diff.materiality import _format_batch

        entries = [
            DiffEntry(
                change_kind="modified",
                clause_ref="Pasal 5",
                before_text="Hubungi kreator@example.com untuk konfirmasi.",
                after_text="Hubungi kreator2@example.com untuk konfirmasi.",
            )
        ]
        redaction_map: dict[str, str] = {}
        batch_text = _format_batch(entries, redaction_map)

        assert "kreator@example.com" not in batch_text
        assert "kreator2@example.com" not in batch_text
        assert "[EMAIL_1]" in batch_text
        assert "[EMAIL_2]" in batch_text
        assert redaction_map["[EMAIL_1]"] == "kreator@example.com"
        assert redaction_map["[EMAIL_2]"] == "kreator2@example.com"

    def test_reuses_version_scoped_mapping(self):
        from landy.diff.compute import DiffEntry
        from landy.diff.materiality import _format_batch

        redaction_map = {"[EMAIL_1]": "kreator@example.com"}
        entries = [
            DiffEntry(
                change_kind="modified",
                clause_ref="Pasal 5",
                before_text="kreator@example.com",
                after_text=None,
            )
        ]
        batch_text = _format_batch(entries, redaction_map)
        assert "[EMAIL_1]" in batch_text
        assert "kreator@example.com" not in batch_text
        # no duplicate token minted for an already-known original
        assert "[EMAIL_2]" not in batch_text


# ── Comment path: pipeline._format_comments ─────────────────────────────────

class TestFormatCommentsRedacts:
    def test_pii_in_comment_body_and_author_is_redacted(self):
        from landy.analysis.pipeline import _format_comments

        comments = [
            {
                "author": "budi@example.com",
                "body": "Silakan hubungi saya di 081234567890 untuk klarifikasi.",
                "anchor_text": "klausul pembayaran",
            }
        ]
        redaction_map: dict[str, str] = {}
        formatted = _format_comments(comments, redaction_map)

        assert "budi@example.com" not in formatted
        assert "081234567890" not in formatted
        assert "[EMAIL_1]" in formatted
        assert any(v == "budi@example.com" for v in redaction_map.values())
        assert any(v == "081234567890" for v in redaction_map.values())

    def test_empty_comments_returns_empty_string(self):
        from landy.analysis.pipeline import _format_comments
        assert _format_comments([], {}) == ""


# ── Email path: export/email_draft.py ───────────────────────────────────────

class TestEmailDraftRedactsBeforeSending:
    """Exercises generate_email_draft with a stub LLM client (no network)."""

    def _stub_llm(self, captured: dict, echo_token: str | None = None):
        class _Completion:
            def __init__(self, content):
                self.content = content
                self.input_tokens = 10
                self.output_tokens = 10
                self.model = "stub-model"

        class _StubClient:
            def chat_complete(self_inner, messages, **kwargs):
                captured["messages"] = messages
                if echo_token:
                    content = f'{{"email": "Draf email menyebut {echo_token}."}}'
                else:
                    content = '{"email": "Draf email negosiasi."}'
                return _Completion(content)

        return _StubClient()

    def test_flag_text_redacted_before_chat_complete(self, monkeypatch):
        import landy.export.email_draft as mod

        captured: dict = {}
        monkeypatch.setattr(mod, "get_llm_client", lambda: self._stub_llm(captured))

        flags = [
            {
                "domain": "payment",
                "severity": "high",
                "summary": "Kontak brand: brand@example.com untuk negosiasi ulang.",
                "negotiation_ask": "Mohon revisi jadwal pembayaran.",
                "finding_type": "present_risky",
            }
        ]

        draft = mod.generate_email_draft(
            document_title="Kontrak Kerjasama",
            counterparty="Brand X",
            flags=flags,
        )

        sent_content = " ".join(m["content"] for m in captured["messages"])
        assert "brand@example.com" not in sent_content
        assert "[EMAIL_1]" in sent_content
        assert draft  # draft still produced

    def test_leaked_token_in_llm_output_is_expanded_back(self, monkeypatch):
        """If the model echoes a token, the returned draft restores the real value."""
        import landy.export.email_draft as mod

        captured: dict = {}
        monkeypatch.setattr(
            mod, "get_llm_client", lambda: self._stub_llm(captured, echo_token="[EMAIL_1]")
        )

        flags = [
            {
                "domain": "payment",
                "severity": "high",
                "summary": "Kontak: brand@example.com",
                "negotiation_ask": "Revisi jadwal pembayaran.",
                "finding_type": "present_risky",
            }
        ]

        draft = mod.generate_email_draft(
            document_title="Kontrak",
            counterparty="Brand X",
            flags=flags,
        )
        assert "brand@example.com" in draft
        assert "[EMAIL_1]" not in draft


pytestmark_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping DB-backed redaction-mapping test",
)


@pytestmark_db
class TestEmailDraftReusesVersionScopedMapping:
    """Confirms generate_email_draft(version_id=...) reuses/persists the
    version's redaction_mappings row set instead of minting an independent
    token space."""

    def test_reuses_existing_token_and_persists_new_ones(self, monkeypatch):
        import sqlalchemy as sa
        from landy.database import engine
        import landy.export.email_draft as mod

        version_id = str(uuid.uuid4())
        # Seed an existing mapping for this version, as the worker's
        # document-level redact() pass would have done.
        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
            conn.execute(
                sa.text(
                    "INSERT INTO redaction_mappings (version_id, token, original) "
                    "VALUES (:vid, '[EMAIL_1]', 'brand@example.com')"
                ),
                {"vid": version_id},
            )

        captured: dict = {}

        class _Completion:
            content = '{"email": "Draf email."}'
            input_tokens = 5
            output_tokens = 5
            model = "stub-model"

        class _StubClient:
            def chat_complete(self_inner, messages, **kwargs):
                captured["messages"] = messages
                return _Completion()

        monkeypatch.setattr(mod, "get_llm_client", lambda: _StubClient())

        flags = [
            {
                "domain": "payment",
                "severity": "high",
                # Same original as the seeded mapping, plus a brand-new one.
                "summary": "Kontak brand@example.com dan legal@example.com",
                "negotiation_ask": "Revisi.",
                "finding_type": "present_risky",
            }
        ]

        mod.generate_email_draft(
            document_title="Kontrak",
            counterparty="Brand X",
            flags=flags,
            version_id=version_id,
        )

        sent_content = " ".join(m["content"] for m in captured["messages"])
        assert "[EMAIL_1]" in sent_content  # reused, not reassigned
        assert "[EMAIL_2]" in sent_content  # new original gets a fresh token
        assert "brand@example.com" not in sent_content
        assert "legal@example.com" not in sent_content

        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
            rows = conn.execute(
                sa.text(
                    "SELECT token, original FROM redaction_mappings WHERE version_id = :vid"
                ),
                {"vid": version_id},
            ).fetchall()
            mapping = {r.token: r.original for r in rows}

        assert mapping["[EMAIL_1]"] == "brand@example.com"
        assert mapping["[EMAIL_2]"] == "legal@example.com"

        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL app.current_user_id = 'SYSTEM_WORKER'"))
            conn.execute(
                sa.text("DELETE FROM redaction_mappings WHERE version_id = :vid"),
                {"vid": version_id},
            )
