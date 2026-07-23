"""Unit tests for DOCX tracked-change generation (docx_export.py).

Tests cover:
- Single edit that matches → one tracked change, no comment-only
- Multiple edits on same clause (both match) → both in one paragraph, no duplication
- Missing original_text → comment-only, no tracked change, no fake formatting
- Mixed: one match + one miss → one tracked change + one comment-only in same paragraph
- Final reconstructed text correctness (no duplication, no missing text)
- DOCX zip structure validity (w:del, w:ins, trackChanges, comments.xml)

Run with:
    python -m pytest tests/test_docx_export.py -v
"""
import io
import zipfile

import pytest
from lxml import etree

from landy.export.docx_export import (
    ClauseData,
    EditData,
    _W,
    build_redlined_docx,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_docx_parts(docx_bytes: bytes) -> dict[str, bytes]:
    """Return dict of part_name → raw bytes from the DOCX zip."""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _doc_xml(parts: dict[str, bytes]) -> etree._Element:
    return etree.fromstring(parts["word/document.xml"])


def _text_content(el: etree._Element) -> str:
    """Extract all text from <w:t> and <w:delText> elements in a subtree."""
    ns = {"w": _W}
    texts = el.findall(".//w:t", ns) + el.findall(".//w:delText", ns)
    return "".join(t.text or "" for t in texts)


def _count_elements(parts: dict[str, bytes], tag: str) -> int:
    """Count how many times a w:-namespace tag appears in document.xml."""
    doc = _doc_xml(parts)
    return len(doc.findall(f".//{{{_W}}}{tag}"))


def _paragraphs(parts: dict[str, bytes]) -> list[etree._Element]:
    doc = _doc_xml(parts)
    body = doc.find(f"{{{_W}}}body")
    return [el for el in body if el.tag == f"{{{_W}}}p"]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSingleEdit:
    """Single suggested edit that matches verbatim."""

    def setup_method(self):
        clauses = [ClauseData(id="c1", ordinal=1, heading_path=None,
                              text="Kreator menyerahkan semua hak IP kepada Brand.")]
        edits = [EditData(id="e1", clause_id="c1",
                          original_text="menyerahkan semua hak IP",
                          revised_text="memberikan lisensi terbatas",
                          comment="Hak moral inalienable")]
        self.docx, self.tc, self.co = build_redlined_docx("Test", clauses, edits)
        self.parts = _extract_docx_parts(self.docx)

    def test_tracked_change_count(self):
        assert self.tc == 1
        assert self.co == 0

    def test_has_del_and_ins(self):
        assert _count_elements(self.parts, "del") >= 1
        assert _count_elements(self.parts, "ins") >= 1

    def test_del_text_contains_original(self):
        doc = _doc_xml(self.parts)
        del_texts = doc.findall(f".//{{{_W}}}delText")
        combined = "".join(t.text or "" for t in del_texts)
        assert "menyerahkan semua hak IP" in combined

    def test_ins_text_contains_revised(self):
        doc = _doc_xml(self.parts)
        ins_els = doc.findall(f".//{{{_W}}}ins")
        combined = "".join(_text_content(el) for el in ins_els)
        assert "memberikan lisensi terbatas" in combined

    def test_comment_range_anchors_present(self):
        assert _count_elements(self.parts, "commentRangeStart") >= 1
        assert _count_elements(self.parts, "commentRangeEnd") >= 1
        assert _count_elements(self.parts, "commentReference") >= 1

    def test_comments_xml_has_comment(self):
        comments_xml = etree.fromstring(self.parts["word/comments.xml"])
        comment_els = comments_xml.findall(f"{{{_W}}}comment")
        # At least: disclaimer comment + one edit comment
        assert len(comment_els) >= 2

    def test_settings_has_track_changes(self):
        settings = self.parts["word/settings.xml"].decode()
        assert "trackChanges" in settings

    def test_valid_docx_zip_structure(self):
        assert "[Content_Types].xml" in self.parts
        assert "word/document.xml" in self.parts
        assert "word/comments.xml" in self.parts
        assert "word/_rels/document.xml.rels" in self.parts


class TestMultipleEditsOnSameClause:
    """Two edits on the same clause — CRITICAL: must not duplicate/omit text."""

    CLAUSE_TEXT = "Masa berlaku kontrak adalah 2 tahun dan dapat diperpanjang secara otomatis."

    def setup_method(self):
        clauses = [ClauseData(id="c1", ordinal=1, heading_path=None, text=self.CLAUSE_TEXT)]
        edits = [
            EditData(id="e1", clause_id="c1",
                     original_text="2 tahun",
                     revised_text="1 tahun",
                     comment="Kurangi masa berlaku"),
            EditData(id="e2", clause_id="c1",
                     original_text="secara otomatis",
                     revised_text="dengan persetujuan tertulis",
                     comment="Harus ada persetujuan eksplisit"),
        ]
        self.docx, self.tc, self.co = build_redlined_docx("Test", clauses, edits)
        self.parts = _extract_docx_parts(self.docx)

    def test_both_tracked_changes_counted(self):
        assert self.tc == 2, f"Expected 2 tracked changes, got {self.tc}"
        assert self.co == 0

    def test_both_deletions_present(self):
        doc = _doc_xml(self.parts)
        del_texts = doc.findall(f".//{{{_W}}}delText")
        combined = "".join(t.text or "" for t in del_texts)
        assert "2 tahun" in combined
        assert "secara otomatis" in combined

    def test_both_insertions_present(self):
        doc = _doc_xml(self.parts)
        ins_els = doc.findall(f".//{{{_W}}}ins")
        combined = "".join(_text_content(el) for el in ins_els)
        assert "1 tahun" in combined
        assert "dengan persetujuan tertulis" in combined

    def test_no_text_duplication(self):
        """The full clause text reconstructed from the paragraph must appear exactly once.
        'Masa berlaku kontrak adalah' is a non-edited prefix that should appear once."""
        doc = _doc_xml(self.parts)
        # Collect all body paragraphs' full text content (t + delText)
        body = doc.find(f"{{{_W}}}body")
        all_para_texts = []
        for p in body.findall(f"{{{_W}}}p"):
            all_para_texts.append(_text_content(p))
        combined = "".join(all_para_texts)
        # "Masa berlaku kontrak adalah" appears in the preamble before first edit
        count = combined.count("Masa berlaku kontrak adalah")
        assert count == 1, (
            f"Expected prefix to appear exactly once, got {count}. "
            f"Combined text: {combined!r}"
        )

    def test_single_clause_produces_one_clause_paragraph(self):
        """All edits for one clause must be in ONE paragraph — not duplicated paragraphs."""
        # Count paragraphs that contain a w:del element (= clauses with tracked changes)
        doc = _doc_xml(self.parts)
        body = doc.find(f"{{{_W}}}body")
        clause_paras_with_del = [
            p for p in body.findall(f"{{{_W}}}p")
            if p.find(f".//{{{_W}}}del") is not None
        ]
        # Both edits are on the same clause — should be in exactly ONE paragraph
        assert len(clause_paras_with_del) == 1, (
            f"Expected 1 paragraph with tracked changes for single clause, "
            f"got {len(clause_paras_with_del)}"
        )


class TestMissingOriginalTextFallback:
    """When original_text is not found verbatim, must use comment-only — never fake formatting."""

    def setup_method(self):
        clauses = [ClauseData(id="c1", ordinal=1, heading_path=None,
                              text="Brand berhak memutus kontrak kapan saja.")]
        edits = [EditData(id="e1", clause_id="c1",
                          original_text="TEKS YANG TIDAK ADA SAMA SEKALI",
                          revised_text="pengganti teks",
                          comment="Usulan yang tidak match")]
        self.docx, self.tc, self.co = build_redlined_docx("Test", clauses, edits)
        self.parts = _extract_docx_parts(self.docx)

    def test_no_tracked_change(self):
        assert self.tc == 0, f"Expected 0 tracked changes, got {self.tc}"
        assert self.co == 1

    def test_no_del_or_ins_elements(self):
        """No w:del or w:ins in the body — this would be fake formatting."""
        doc = _doc_xml(self.parts)
        body = doc.find(f"{{{_W}}}body")
        clause_paras = [p for p in body.findall(f"{{{_W}}}p")
                        if _text_content(p).strip() not in ("", "Test") and
                        "LANDY Creator" not in _text_content(p) and
                        "PENTING:" not in _text_content(p)]
        for p in clause_paras:
            dels = p.findall(f".//{{{_W}}}del")
            ins = p.findall(f".//{{{_W}}}ins")
            assert not dels, "w:del found in comment-only paragraph — fake formatting!"
            assert not ins, "w:ins found in comment-only paragraph — fake formatting!"

    def test_clause_text_fully_preserved(self):
        """The original clause text must still be present (no deletion of unmatched text)."""
        doc = _doc_xml(self.parts)
        all_text = _text_content(doc)
        assert "Brand berhak memutus kontrak kapan saja." in all_text

    def test_comment_reference_present(self):
        assert _count_elements(self.parts, "commentReference") >= 2  # disclaimer + edit comment


class TestMixedMatchAndMiss:
    """One edit matches, one doesn't — both applied to the same clause paragraph."""

    CLAUSE_TEXT = "Kreator memberikan hak IP penuh. Kontrak berlaku tanpa batas waktu."

    def setup_method(self):
        clauses = [ClauseData(id="c1", ordinal=1, heading_path=None, text=self.CLAUSE_TEXT)]
        edits = [
            EditData(id="e1", clause_id="c1",
                     original_text="hak IP penuh",
                     revised_text="lisensi terbatas",
                     comment="Jangan full IP transfer"),
            EditData(id="e2", clause_id="c1",
                     original_text="KLAUSUL YANG TIDAK ADA",
                     revised_text="pengganti",
                     comment="Tidak ditemukan"),
        ]
        self.docx, self.tc, self.co = build_redlined_docx("Test", clauses, edits)
        self.parts = _extract_docx_parts(self.docx)

    def test_counts(self):
        assert self.tc == 1, f"Expected 1 tracked change, got {self.tc}"
        assert self.co == 1, f"Expected 1 comment-only, got {self.co}"

    def test_matched_edit_produces_del_ins(self):
        doc = _doc_xml(self.parts)
        del_texts = doc.findall(f".//{{{_W}}}delText")
        combined = "".join(t.text or "" for t in del_texts)
        assert "hak IP penuh" in combined

    def test_original_text_present_once(self):
        """'Kreator memberikan' (preamble) must appear exactly once — no duplication."""
        doc = _doc_xml(self.parts)
        all_text = _text_content(doc)
        count = all_text.count("Kreator memberikan")
        assert count == 1, f"Expected 1 occurrence, got {count}. Text: {all_text!r}"

    def test_both_in_one_paragraph(self):
        """Matched + unmatched edits on same clause → one paragraph, no extra empty para."""
        doc = _doc_xml(self.parts)
        body = doc.find(f"{{{_W}}}body")
        clause_paras = [
            p for p in body.findall(f"{{{_W}}}p")
            if "Kreator memberikan" in _text_content(p)
        ]
        assert len(clause_paras) == 1, (
            f"Expected clause text in exactly 1 paragraph, got {len(clause_paras)}"
        )
