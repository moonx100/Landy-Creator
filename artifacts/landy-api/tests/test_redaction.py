"""Tests for landy.redaction — no DB required.

Covers the PHONE-pattern trailing-whitespace bug: `[0-9\\s\\-]{6,13}` used to
greedily consume trailing separators/whitespace after the last digit of a
phone number when followed by non-digit text, corrupting both the redacted
text (a token that swallowed the following space) and the stored mapping
(an original value with trailing whitespace baked in, which `expand()` would
then re-inject into exported documents).
"""
from __future__ import annotations

from landy.redaction import expand, redact


class TestPhoneRedaction:
    def test_phone_followed_by_word_does_not_swallow_trailing_space(self):
        result = redact("Silakan hubungi saya di 081234567890 untuk klarifikasi.")

        assert "[PHONE_1] untuk klarifikasi." in result.redacted_text
        assert result.mapping["[PHONE_1]"] == "081234567890"

    def test_phone_with_dashes_followed_by_comma(self):
        result = redact("Telepon: 0812-3456-7890, terima kasih.")

        assert "[PHONE_1], terima kasih." in result.redacted_text
        assert result.mapping["[PHONE_1]"] == "0812-3456-7890"

    def test_phone_with_spaces_between_groups(self):
        result = redact("Nomor saya 0812 3456 7890 aktif.")

        assert result.mapping["[PHONE_1]"] == "0812 3456 7890"
        assert "[PHONE_1] aktif." in result.redacted_text

    def test_bare_phone_number(self):
        result = redact("081234567890")

        assert result.redacted_text == "[PHONE_1]"
        assert result.mapping["[PHONE_1]"] == "081234567890"

    def test_expand_restores_exact_original_no_extra_whitespace(self):
        original = "Silakan hubungi saya di 081234567890 untuk klarifikasi."
        result = redact(original)
        assert expand(result.redacted_text, result.mapping) == original
