"""DOCX tracked-change (revision mark) parser.

Reads <w:ins> and <w:del> elements from word/document.xml and produces
per-paragraph (original_text, revised_text) pairs.

Spec contract:
  - original_text: paragraph text with deletions kept, insertions stripped.
  - revised_text:  paragraph text with deletions stripped, insertions kept.
  - Only paragraphs with at least one tracked change are returned.
  - Paragraphs where original == revised (whitespace-only diff) are skipped.

This module uses only stdlib (zipfile, xml.etree.ElementTree) — no python-docx
— so we can access the raw revision-mark XML that python-docx discards.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

# WordprocessingML namespace
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class TrackedChange:
    """One paragraph that contains at least one insertion or deletion."""
    paragraph_index: int
    clause_ref: str                    # human-readable label, e.g. "Paragraf 7"
    original_text: str                 # deletions retained, insertions stripped
    revised_text: str                  # insertions retained, deletions stripped
    authors: list[str] = field(default_factory=list)


@dataclass
class TrackedChangesResult:
    has_changes: bool
    changes: list[TrackedChange]
    # Operational outcome, distinct from the semantic answer. parse_ok=False
    # means "we could not read the revision layer" — which must never be
    # collapsed into has_changes=False ("we read it and there are none").
    parse_ok: bool = True
    parse_note: Optional[str] = None


def parse_tracked_changes(file_bytes: bytes) -> TrackedChangesResult:
    """Parse tracked changes from a DOCX file.

    Returns has_changes=False with parse_ok=True only when the document was
    genuinely readable and carries no <w:ins>/<w:del> (or only whitespace
    diffs). A file we could not read — invalid ZIP, missing or malformed
    word/document.xml — returns parse_ok=False with a populated parse_note.

    Never raises; failure is representable in the result instead.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            namelist = zf.namelist()
            if "word/document.xml" not in namelist:
                # A DOCX without its main part is a malformed file, not a
                # document with no revisions.
                return TrackedChangesResult(
                    has_changes=False, changes=[], parse_ok=False,
                    parse_note="Berkas DOCX tidak memiliki word/document.xml",
                )
            doc_xml = zf.read("word/document.xml")
    except Exception as exc:
        return TrackedChangesResult(
            has_changes=False, changes=[], parse_ok=False,
            parse_note=f"Berkas bukan DOCX/ZIP yang valid: {exc}",
        )

    try:
        root = ET.fromstring(doc_xml)
    except ET.ParseError as exc:
        return TrackedChangesResult(
            has_changes=False, changes=[], parse_ok=False,
            parse_note=f"XML dokumen tidak dapat dibaca: {exc}",
        )

    body = root.find(f".//{_W}body")
    if body is None:
        return TrackedChangesResult(
            has_changes=False, changes=[], parse_ok=False,
            parse_note="Struktur dokumen tidak memiliki elemen body",
        )

    changes: list[TrackedChange] = []
    para_idx = 0

    for elem in body:
        if elem.tag != f"{_W}p":
            continue

        orig_text, rev_text, has_tc, authors = _extract_paragraph(elem)

        if has_tc and orig_text != rev_text:
            changes.append(TrackedChange(
                paragraph_index=para_idx,
                clause_ref=f"Paragraf {para_idx + 1}",
                original_text=orig_text,
                revised_text=rev_text,
                authors=authors,
            ))

        para_idx += 1

    return TrackedChangesResult(has_changes=bool(changes), changes=changes)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_paragraph(
    para: ET.Element,
) -> tuple[str, str, bool, list[str]]:
    """Return (original_text, revised_text, has_tc, authors) for a paragraph.

    Walks the element tree recursively.  State variables track whether the
    current node is inside a <w:ins> or <w:del> scope:
      - <w:t> in normal context → append to both orig and rev.
      - <w:t> inside <w:ins>   → append to rev only.
      - <w:delText> inside <w:del> → append to orig only.
    """
    orig: list[str] = []
    rev: list[str] = []
    has_tc = False
    authors: set[str] = set()

    def visit(elem: ET.Element, in_ins: bool, in_del: bool) -> None:
        nonlocal has_tc
        tag = elem.tag

        if tag == f"{_W}ins":
            has_tc = True
            a = elem.get(f"{_W}author") or ""
            if a:
                authors.add(a)
            for child in elem:
                visit(child, True, False)
            return

        if tag == f"{_W}del":
            has_tc = True
            a = elem.get(f"{_W}author") or ""
            if a:
                authors.add(a)
            for child in elem:
                visit(child, False, True)
            return

        if tag == f"{_W}t":
            # xml:space="preserve" honoured by ElementTree — text may include spaces
            text = elem.text or ""
            if not in_ins and not in_del:
                orig.append(text)
                rev.append(text)
            elif in_ins:
                rev.append(text)
            # in_del + w:t: unusual; per OOXML spec text lives in w:delText — skip
            return

        if tag == f"{_W}delText":
            text = elem.text or ""
            if in_del:
                orig.append(text)
            return

        # Recurse into anything else (w:r, w:hyperlink, w:sdt, etc.)
        for child in elem:
            visit(child, in_ins, in_del)

    for child in para:
        visit(child, False, False)

    return (
        "".join(orig).strip(),
        "".join(rev).strip(),
        has_tc,
        sorted(authors),
    )
