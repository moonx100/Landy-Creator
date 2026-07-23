"""Unit tests for version diff computation (landy/diff/compute.py).

Tests cover:
- No changes between identical versions → empty list
- Single modification → one 'modified' entry
- Added clause → one 'added' entry
- Removed clause → one 'removed' entry
- Mixed: modified + added + removed in one diff
- Replace block with unequal side lengths (more added than removed, etc.)
- Whitespace-only difference → skipped (not a diff entry)
- clause_ref falls back to "Klausul N" when heading_path is absent

Run with:
    python -m pytest tests/test_version_diff.py -v
"""
import pytest
from landy.diff.compute import compute_clause_diff, DiffEntry


def _clause(ordinal: int, text: str, heading_path: str | None = None) -> dict:
    return {
        "id": f"c{ordinal}",
        "ordinal": ordinal,
        "heading_path": heading_path,
        "text": text,
    }


# ── Identical versions ─────────────────────────────────────────────────────────

class TestNoChanges:
    def test_empty_versions(self):
        result = compute_clause_diff([], [])
        assert result == []

    def test_identical_single(self):
        c = [_clause(1, "Kreator menyerahkan IP.")]
        assert compute_clause_diff(c, c) == []

    def test_identical_multiple(self):
        clauses = [
            _clause(1, "Klausul satu.", "Pasal 1"),
            _clause(2, "Klausul dua.", "Pasal 2"),
            _clause(3, "Klausul tiga.", "Pasal 3"),
        ]
        assert compute_clause_diff(clauses, clauses) == []


# ── Single modification ────────────────────────────────────────────────────────

class TestModified:
    def setup_method(self):
        self.old = [_clause(1, "Masa berlaku 2 tahun.", "Pasal 5")]
        self.new = [_clause(1, "Masa berlaku 1 tahun.", "Pasal 5")]
        self.result = compute_clause_diff(self.old, self.new)

    def test_one_entry(self):
        assert len(self.result) == 1

    def test_change_kind(self):
        assert self.result[0].change_kind == "modified"

    def test_clause_ref_uses_heading_path(self):
        assert self.result[0].clause_ref == "Pasal 5"

    def test_before_and_after_text(self):
        assert self.result[0].before_text == "Masa berlaku 2 tahun."
        assert self.result[0].after_text == "Masa berlaku 1 tahun."


# ── Added clause ───────────────────────────────────────────────────────────────

class TestAdded:
    def setup_method(self):
        self.old = [_clause(1, "Klausul bestaan.", "Pasal 1")]
        self.new = [
            _clause(1, "Klausul bestaan.", "Pasal 1"),
            _clause(2, "Klausul kerahasiaan baru.", "Pasal 2"),
        ]
        self.result = compute_clause_diff(self.old, self.new)

    def test_one_entry(self):
        assert len(self.result) == 1

    def test_change_kind(self):
        assert self.result[0].change_kind == "added"

    def test_no_before_text(self):
        assert self.result[0].before_text is None

    def test_after_text_present(self):
        assert self.result[0].after_text == "Klausul kerahasiaan baru."

    def test_clause_ref(self):
        assert self.result[0].clause_ref == "Pasal 2"


# ── Removed clause ─────────────────────────────────────────────────────────────

class TestRemoved:
    def setup_method(self):
        self.old = [
            _clause(1, "Klausul A.", "Pasal 1"),
            _clause(2, "Klausul yang dihapus.", "Pasal 2"),
        ]
        self.new = [_clause(1, "Klausul A.", "Pasal 1")]
        self.result = compute_clause_diff(self.old, self.new)

    def test_one_entry(self):
        assert len(self.result) == 1

    def test_change_kind(self):
        assert self.result[0].change_kind == "removed"

    def test_before_text_present(self):
        assert self.result[0].before_text == "Klausul yang dihapus."

    def test_no_after_text(self):
        assert self.result[0].after_text is None


# ── Mixed diff ─────────────────────────────────────────────────────────────────

class TestMixed:
    """Modified clauses plus a genuine add (new clause at the end) in one version pair.

    SequenceMatcher pairs same-position clauses as 'replace' (→ 'modified')
    when the sequence lengths are equal or when the divergence is at the same
    position.  A genuine 'added' entry only appears when the new list is longer
    than the old — i.e. a clause was inserted that has no positional counterpart.
    """

    def setup_method(self):
        self.old = [
            _clause(1, "IP diserahkan penuh.", "Pasal 1"),
            _clause(2, "Pembayaran 30 hari.", "Pasal 2"),
        ]
        self.new = [
            _clause(1, "IP: lisensi terbatas.", "Pasal 1"),  # modified
            _clause(2, "Pembayaran 30 hari.", "Pasal 2"),   # unchanged
            _clause(3, "Klausul kerahasiaan baru.", "Pasal 3"),  # purely added
        ]
        self.result = compute_clause_diff(self.old, self.new)

    def test_entry_count(self):
        # modified (Pasal 1) + added (Pasal 3) = 2
        assert len(self.result) == 2, f"Got: {[(e.change_kind, e.clause_ref) for e in self.result]}"

    def test_contains_modified(self):
        kinds = [e.change_kind for e in self.result]
        assert "modified" in kinds

    def test_contains_added(self):
        kinds = [e.change_kind for e in self.result]
        assert "added" in kinds

    def test_unchanged_not_in_result(self):
        refs = [e.clause_ref for e in self.result]
        assert "Pasal 2" not in refs, "Unchanged clause should not appear in diff"


class TestSamePositionReplace:
    """Two same-length versions where one clause completely changes content.

    SequenceMatcher treats this as a replace block → 'modified'.
    This is the correct behavior: the creator sees the clause was changed,
    not that the old one was deleted and a new one added.
    """

    def setup_method(self):
        self.old = [
            _clause(1, "Klausul A.", "Pasal 1"),
            _clause(2, "Klausul non-kompetisi 2 tahun.", "Pasal 2"),
        ]
        self.new = [
            _clause(1, "Klausul A.", "Pasal 1"),    # unchanged
            _clause(2, "Klausul kerahasiaan baru.", "Pasal 2"),  # modified
        ]
        self.result = compute_clause_diff(self.old, self.new)

    def test_one_modified_entry(self):
        assert len(self.result) == 1
        assert self.result[0].change_kind == "modified"

    def test_before_and_after_texts(self):
        assert "non-kompetisi" in self.result[0].before_text
        assert "kerahasiaan" in self.result[0].after_text


# ── Unequal replace blocks ─────────────────────────────────────────────────────

class TestUnequalReplaceBlock:
    """Replace block with more new clauses than old → some are added, not modified."""

    def setup_method(self):
        # 1 old clause replaced by 3 new clauses
        self.old = [_clause(1, "Satu klausul.")]
        self.new = [
            _clause(1, "Versi baru klausul pertama."),
            _clause(2, "Klausul kedua baru."),
            _clause(3, "Klausul ketiga baru."),
        ]
        self.result = compute_clause_diff(self.old, self.new)

    def test_one_modified_two_added(self):
        kinds = [e.change_kind for e in self.result]
        assert kinds.count("modified") == 1
        assert kinds.count("added") == 2

    def test_total_entries(self):
        assert len(self.result) == 3


class TestMoreRemovedThanAdded:
    """Replace block with more old clauses than new → some are removed, not modified."""

    def setup_method(self):
        self.old = [
            _clause(1, "Klausul satu."),
            _clause(2, "Klausul dua."),
            _clause(3, "Klausul tiga."),
        ]
        self.new = [_clause(1, "Hanya satu klausul pengganti.")]
        self.result = compute_clause_diff(self.old, self.new)

    def test_one_modified_two_removed(self):
        kinds = [e.change_kind for e in self.result]
        assert kinds.count("modified") == 1
        assert kinds.count("removed") == 2

    def test_total_entries(self):
        assert len(self.result) == 3


# ── Whitespace only ────────────────────────────────────────────────────────────

class TestWhitespaceOnly:
    def test_whitespace_diff_skipped(self):
        old = [_clause(1, "  Klausul dengan spasi.  ")]
        new = [_clause(1, "Klausul dengan spasi.")]
        result = compute_clause_diff(old, new)
        assert result == [], f"Whitespace-only diff should be skipped: {result}"


# ── clause_ref fallback ────────────────────────────────────────────────────────

class TestClauseRefFallback:
    def test_fallback_to_ordinal_when_no_heading(self):
        old = [_clause(7, "Teks lama.", heading_path=None)]
        new = [_clause(7, "Teks baru.", heading_path=None)]
        result = compute_clause_diff(old, new)
        assert len(result) == 1
        assert result[0].clause_ref == "Klausul 7"

    def test_heading_path_used_when_available(self):
        old = [_clause(3, "Lama.", "Ayat 3.2")]
        new = [_clause(3, "Baru.", "Ayat 3.2")]
        result = compute_clause_diff(old, new)
        assert result[0].clause_ref == "Ayat 3.2"
