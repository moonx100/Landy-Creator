"""Generate a DOCX with genuine OOXML tracked changes from suggested edits.

Spec §8a non-negotiables:
- w:del/w:ins elements with w:id, w:author, w:date — NEVER fake blue/bold or strikethrough
- Each tracked change anchored to a real Word comment (w:commentRangeStart/End)
- If original_text not found in clause → comment only, no fake formatting
- Disclaimer injected as a first-page comment

Implementation strategy:
  Build the DOCX from scratch as a valid OOXML package (zip file) using lxml
  for document.xml and comments.xml, plus minimal static XML for the rest.
  This avoids modifying python-docx output and gives full control over markup.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Optional

from lxml import etree

# ── Constants ─────────────────────────────────────────────────────────────────

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "http://www.w3.org/XML/1998/namespace"
_AUTHOR = "LANDY Creator"
_DATE = "2024-01-01T00:00:00Z"  # fixed date → diffs are reproducible

_DISCLAIMER = (
    "PENTING: Dokumen ini adalah informasi hukum dan panduan negosiasi, "
    "BUKAN nasihat hukum. Dokumen ini BUKAN pengganti konsultasi dengan Advokat "
    "berlisensi. Dihasilkan oleh LANDY Creator — langganan gratis beta."
)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ClauseData:
    id: str
    ordinal: int
    heading_path: Optional[str]
    text: str  # expanded (redaction tokens restored)


@dataclass
class EditData:
    id: str
    clause_id: Optional[str]
    original_text: str
    revised_text: str
    comment: Optional[str]


# ── lxml element helpers ──────────────────────────────────────────────────────

def _w(tag: str) -> str:
    """Return Clark-notation tag in the w: namespace."""
    return f"{{{_W}}}{tag}"


def _set(el: etree._Element, attr: str, val: str) -> None:
    """Set a w:-namespaced attribute on an element."""
    el.set(f"{{{_W}}}{attr}", val)


def _run(text: str, *, del_run: bool = False) -> etree._Element:
    """Return a <w:r> element with a <w:t> or <w:delText> child."""
    r = etree.Element(_w("r"))
    child_tag = _w("delText") if del_run else _w("t")
    t = etree.SubElement(r, child_tag)
    t.text = text
    t.set(f"{{{_XML_SPACE}}}space", "preserve")
    return r


def _del_element(text: str, change_id: int) -> etree._Element:
    """<w:del w:id=N w:author=... w:date=...><w:r><w:delText>text</w:delText></w:r></w:del>"""
    el = etree.Element(_w("del"))
    _set(el, "id", str(change_id))
    _set(el, "author", _AUTHOR)
    _set(el, "date", _DATE)
    el.append(_run(text, del_run=True))
    return el


def _ins_element(text: str, change_id: int) -> etree._Element:
    """<w:ins w:id=N w:author=... w:date=...><w:r><w:t>text</w:t></w:r></w:ins>"""
    el = etree.Element(_w("ins"))
    _set(el, "id", str(change_id))
    _set(el, "author", _AUTHOR)
    _set(el, "date", _DATE)
    el.append(_run(text))
    return el


def _comment_range_start(cid: int) -> etree._Element:
    el = etree.Element(_w("commentRangeStart"))
    _set(el, "id", str(cid))
    return el


def _comment_range_end(cid: int) -> etree._Element:
    el = etree.Element(_w("commentRangeEnd"))
    _set(el, "id", str(cid))
    return el


def _comment_reference(cid: int) -> etree._Element:
    """A run containing a w:commentReference — links the paragraph to the comment."""
    r = etree.Element(_w("r"))
    rpr = etree.SubElement(r, _w("rPr"))
    style = etree.SubElement(rpr, _w("rStyle"))
    _set(style, "val", "CommentReference")
    ref = etree.SubElement(r, _w("commentReference"))
    _set(ref, "id", str(cid))
    return r


# ── Paragraph builders ────────────────────────────────────────────────────────

def _plain_paragraph(text: str, style: str = "Normal") -> etree._Element:
    """Build a <w:p> with a single run and no tracked changes."""
    p = etree.Element(_w("p"))
    ppr = etree.SubElement(p, _w("pPr"))
    ps = etree.SubElement(ppr, _w("pStyle"))
    _set(ps, "val", style)
    if text:
        p.append(_run(text))
    return p


def _tracked_change_paragraph(
    before: str,
    original: str,
    revised: str,
    after: str,
    comment_id: int,
    change_id_base: int,
    style: str = "Normal",
) -> etree._Element:
    """Build a <w:p> with del/ins tracked change and comment anchors."""
    p = etree.Element(_w("p"))
    ppr = etree.SubElement(p, _w("pPr"))
    ps = etree.SubElement(ppr, _w("pStyle"))
    _set(ps, "val", style)

    if before:
        p.append(_run(before))
    p.append(_comment_range_start(comment_id))
    p.append(_del_element(original, change_id_base))
    p.append(_ins_element(revised, change_id_base + 1))
    p.append(_comment_range_end(comment_id))
    p.append(_comment_reference(comment_id))
    if after:
        p.append(_run(after))
    return p


def _comment_paragraph_only(
    clause_text: str,
    comment_id: int,
    comment_label: str,
    style: str = "Normal",
) -> etree._Element:
    """When original_text not found: write clause as-is + comment anchor at end.
    The tracked change surfaces as a comment only (per spec §8a last sentence).
    """
    p = etree.Element(_w("p"))
    ppr = etree.SubElement(p, _w("pPr"))
    ps = etree.SubElement(ppr, _w("pStyle"))
    _set(ps, "val", style)

    p.append(_comment_range_start(comment_id))
    p.append(_run(clause_text))
    p.append(_comment_range_end(comment_id))
    p.append(_comment_reference(comment_id))
    return p


# ── Comments.xml builder ──────────────────────────────────────────────────────

def _build_comments_xml(comments: list[tuple[int, str]]) -> bytes:
    """Build comments.xml content.

    Args:
        comments: list of (comment_id, comment_text)
    """
    NS_MAP = {
        "w": _W,
        "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    root = etree.Element(f"{{{_W}}}comments", nsmap=NS_MAP)

    for cid, ctext in comments:
        comment_el = etree.SubElement(root, _w("comment"))
        _set(comment_el, "id", str(cid))
        _set(comment_el, "author", _AUTHOR)
        _set(comment_el, "date", _DATE)
        _set(comment_el, "initials", "LC")

        cp = etree.SubElement(comment_el, _w("p"))
        cppr = etree.SubElement(cp, _w("pPr"))
        cpstyle = etree.SubElement(cppr, _w("pStyle"))
        _set(cpstyle, "val", "CommentText")

        # annotationRef run (required by OOXML spec for comment bodies)
        anno_r = etree.SubElement(cp, _w("r"))
        anno_rpr = etree.SubElement(anno_r, _w("rPr"))
        anno_rs = etree.SubElement(anno_rpr, _w("rStyle"))
        _set(anno_rs, "val", "CommentReference")
        etree.SubElement(anno_r, _w("annotationRef"))

        # Actual comment text
        text_r = etree.SubElement(cp, _w("r"))
        text_t = etree.SubElement(text_r, _w("t"))
        text_t.text = ctext
        text_t.set(f"{{{_XML_SPACE}}}space", "preserve")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# ── Static package parts ──────────────────────────────────────────────────────

_CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>"""

_PKG_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
</Relationships>"""

_STYLES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:sz w:val="24"/></w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="CommentText">
    <w:name w:val="Comment Text"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:sz w:val="20"/></w:rPr>
  </w:style>
  <w:style w:type="character" w:styleId="CommentReference">
    <w:name w:val="Comment Reference"/>
    <w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="DisclaimerText">
    <w:name w:val="Disclaimer Text"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:i/><w:color w:val="C00000"/></w:rPr>
  </w:style>
</w:styles>"""

_SETTINGS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:trackChanges/>
  <w:defaultTabStop w:val="720"/>
  <w:compat>
    <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
  </w:compat>
</w:settings>"""


# ── Document body builder ─────────────────────────────────────────────────────

def _build_document_xml(
    title: str,
    clauses: list[ClauseData],
    edits_by_clause: dict[str, list[EditData]],
) -> tuple[bytes, list[tuple[int, str]], int, int]:
    """Build the complete document.xml XML.

    Returns:
        (xml_bytes, comments, tracked_change_count, comment_only_count)
        where comments is list of (comment_id, comment_text)
    """
    NS_MAP = {
        "w": _W,
        "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    doc_root = etree.Element(f"{{{_W}}}document", nsmap=NS_MAP)
    body = etree.SubElement(doc_root, _w("body"))

    comments: list[tuple[int, str]] = []
    comment_id_counter = 0
    change_id_counter = 0
    tracked_change_count = 0
    comment_only_count = 0

    # ── Disclaimer comment (id=0) ─────────────────────────────────────────────
    dis_para = _comment_paragraph_only(
        _DISCLAIMER,
        comment_id_counter,
        _DISCLAIMER,
        style="DisclaimerText",
    )
    body.append(dis_para)
    comments.append((comment_id_counter, f"LANDY Creator: {_DISCLAIMER}"))
    comment_id_counter += 1

    # ── Title ─────────────────────────────────────────────────────────────────
    body.append(_plain_paragraph(title, style="Heading1"))

    # ── Clauses ───────────────────────────────────────────────────────────────
    for clause in sorted(clauses, key=lambda c: c.ordinal):
        # Heading (if present)
        if clause.heading_path:
            body.append(_plain_paragraph(clause.heading_path, style="Heading2"))

        clause_edits = edits_by_clause.get(clause.id, [])

        if not clause_edits:
            # No edits — normal paragraph
            body.append(_plain_paragraph(clause.text))
            continue

        # ALL edits for this clause go into ONE <w:p> element.
        # Matched edits: inline del/ins applied sequentially to the remaining text.
        # Unmatched edits (original_text not found): comment anchors appended
        #   AFTER all clause content — never as separate paragraphs.
        # This prevents any duplicated or omitted text regardless of edit count.
        p = etree.Element(_w("p"))
        ppr = etree.SubElement(p, _w("pPr"))
        ps = etree.SubElement(ppr, _w("pStyle"))
        _set(ps, "val", "Normal")

        remaining = clause.text
        pending_comment_only: list[int] = []  # comment_ids for unmatched edits

        for edit in clause_edits:
            pos = remaining.find(edit.original_text)

            if pos == -1:
                # original_text not found → comment only (spec §8a last sentence)
                comment_text = (
                    f"LANDY Creator — Usulan Perubahan:\n"
                    f"Teks asli: {edit.original_text[:200]}\n"
                    f"Usulan: {edit.revised_text[:200]}"
                )
                if edit.comment:
                    comment_text += f"\nCatatan: {edit.comment}"
                comments.append((comment_id_counter, comment_text))
                pending_comment_only.append(comment_id_counter)
                comment_id_counter += 1
                comment_only_count += 1
                continue

            # Match found — emit: [before] [del] [ins] and advance remaining
            before = remaining[:pos]
            after = remaining[pos + len(edit.original_text):]

            if before:
                p.append(_run(before))

            comment_text = "LANDY Creator"
            if edit.comment:
                comment_text += f": {edit.comment}"
            comments.append((comment_id_counter, comment_text))

            p.append(_comment_range_start(comment_id_counter))
            p.append(_del_element(edit.original_text, change_id_counter))
            p.append(_ins_element(edit.revised_text, change_id_counter + 1))
            p.append(_comment_range_end(comment_id_counter))
            p.append(_comment_reference(comment_id_counter))

            comment_id_counter += 1
            change_id_counter += 2  # del uses one id, ins another
            tracked_change_count += 1
            remaining = after  # next edit searches only the post-match remainder

        # Emit any clause text that follows the last matched edit
        if remaining:
            p.append(_run(remaining))

        # Append unmatched edit comment anchors after all content
        # (empty ranges are valid OOXML and surface as pure comment balloons)
        for co_cid in pending_comment_only:
            p.append(_comment_range_start(co_cid))
            p.append(_comment_range_end(co_cid))
            p.append(_comment_reference(co_cid))

        body.append(p)

    # ── Section properties (required for valid OOXML) ─────────────────────────
    sect_pr = etree.SubElement(body, _w("sectPr"))
    pg_sz = etree.SubElement(sect_pr, _w("pgSz"))
    _set(pg_sz, "w", "11906")   # A4 width in twentieths-of-a-point
    _set(pg_sz, "h", "16838")   # A4 height

    xml_bytes = etree.tostring(
        doc_root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    return xml_bytes, comments, tracked_change_count, comment_only_count


# ── Public entry point ────────────────────────────────────────────────────────

def build_redlined_docx(
    title: str,
    clauses: list[ClauseData],
    edits: list[EditData],
) -> tuple[bytes, int, int]:
    """Generate a DOCX with real OOXML tracked changes.

    Args:
        title:    Document title (used as Heading 1).
        clauses:  Clause data with expanded (non-redacted) text.
        edits:    Suggested edits (accepted or undecided) to include.

    Returns:
        (docx_bytes, tracked_change_count, comment_only_count)
    """
    # Group edits by clause_id
    edits_by_clause: dict[str, list[EditData]] = {}
    for edit in edits:
        if edit.clause_id:
            edits_by_clause.setdefault(edit.clause_id, []).append(edit)

    # Build document.xml and collect comments
    doc_xml, comments, tc_count, co_count = _build_document_xml(
        title, clauses, edits_by_clause
    )

    # Build comments.xml
    comments_xml = _build_comments_xml(comments)

    # Assemble DOCX zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _PKG_RELS)
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        zf.writestr("word/styles.xml", _STYLES)
        zf.writestr("word/settings.xml", _SETTINGS)
        zf.writestr("word/comments.xml", comments_xml)

    return buf.getvalue(), tc_count, co_count
