"""DOCX comment bubble parser.

Extracts <w:comment> elements from word/comments.xml and resolves each
comment's anchor text from word/document.xml using <w:commentRangeStart> /
<w:commentRangeEnd> markers.

Spec contract:
  - author:      w:author attribute (may be None).
  - date:        w:date attribute as ISO-8601 string (may be None).
  - anchor_text: text between commentRangeStart and commentRangeEnd; trimmed.
  - body:        full text of the comment paragraph(s); trimmed.

Only first-author, first-text level is parsed.  Reply threads (w:commentRefs
inside comment bodies) are intentionally skipped for beta.

This module uses only stdlib — no python-docx.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class DocComment:
    """One comment bubble extracted from a DOCX."""
    comment_id: str               # w:id attribute — used to correlate with anchors
    author: Optional[str]
    date: Optional[str]           # ISO-8601 string from w:date
    anchor_text: Optional[str]    # text the comment is attached to
    body: str                     # comment text


@dataclass
class CommentsResult:
    comments: list[DocComment]
    # Operational outcome, distinct from the semantic answer. parse_ok=False
    # means "we could not read the comments part" — never to be collapsed
    # into comments=[] ("we read it and there are none").
    parse_ok: bool = True
    parse_note: Optional[str] = None


def parse_comments(file_bytes: bytes) -> CommentsResult:
    """Parse all comment bubbles from a DOCX file.

    Returns an empty list with parse_ok=True only when word/comments.xml is
    genuinely absent (no comments) or every comment body is empty. A file we
    could not read — invalid ZIP, malformed comments XML — returns
    parse_ok=False with a populated parse_note.

    Never raises; failure is representable in the result instead.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            namelist = zf.namelist()
            if "word/comments.xml" not in namelist:
                return CommentsResult(comments=[])
            comments_xml = zf.read("word/comments.xml")
            doc_xml = zf.read("word/document.xml") if "word/document.xml" in namelist else b""
    except Exception as exc:
        return CommentsResult(
            comments=[], parse_ok=False,
            parse_note=f"Berkas bukan DOCX/ZIP yang valid: {exc}",
        )

    # ── Parse comment bodies ──────────────────────────────────────────────────
    try:
        croot = ET.fromstring(comments_xml)
    except ET.ParseError as exc:
        return CommentsResult(
            comments=[], parse_ok=False,
            parse_note=f"XML komentar tidak dapat dibaca: {exc}",
        )

    raw_comments: dict[str, dict] = {}
    for comment_elem in croot.iter(f"{_W}comment"):
        cid = comment_elem.get(f"{_W}id")
        if not cid:
            continue
        author = comment_elem.get(f"{_W}author")
        date = comment_elem.get(f"{_W}date")
        body_text = _collect_text(comment_elem).strip()
        if not body_text:
            continue
        raw_comments[cid] = {"author": author, "date": date, "body": body_text}

    if not raw_comments:
        return CommentsResult(comments=[])

    # ── Resolve anchor texts from document body ───────────────────────────────
    anchor_texts: dict[str, str] = {}
    anchor_note: Optional[str] = None
    if doc_xml:
        try:
            droot = ET.fromstring(doc_xml)
            dbody = droot.find(f".//{_W}body")
            if dbody is not None:
                anchor_texts = _extract_anchors(dbody, set(raw_comments.keys()))
        except ET.ParseError:
            # Comments themselves parsed fine; only the anchor resolution
            # degraded. Surface that in the note without failing the parse.
            anchor_note = "Teks jangkar komentar tidak dapat dibaca"

    # ── Build result list in document order (by comment id, numeric sort) ──────
    try:
        sorted_ids = sorted(raw_comments.keys(), key=lambda x: int(x))
    except ValueError:
        sorted_ids = sorted(raw_comments.keys())

    comments: list[DocComment] = []
    for cid in sorted_ids:
        c = raw_comments[cid]
        comments.append(DocComment(
            comment_id=cid,
            author=c["author"],
            date=c.get("date"),
            anchor_text=anchor_texts.get(cid),
            body=c["body"],
        ))

    return CommentsResult(comments=comments, parse_ok=True, parse_note=anchor_note)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collect_text(elem: ET.Element) -> str:
    """Collect all <w:t> and <w:delText> text within an element subtree."""
    parts: list[str] = []
    for child in elem.iter():
        if child.tag in (f"{_W}t", f"{_W}delText"):
            parts.append(child.text or "")
    return "".join(parts)


def _extract_anchors(body: ET.Element, comment_ids: set[str]) -> dict[str, str]:
    """Walk the document body linearly and collect anchor text for each comment ID.

    Strategy: when we see <w:commentRangeStart w:id="N"/>, begin accumulating
    text; when we see <w:commentRangeEnd w:id="N"/>, flush the accumulated text.
    <w:t> elements encountered while any range is active contribute to all active
    ranges (a character can be inside multiple nested comment ranges).
    """
    anchors: dict[str, str] = {}
    active: dict[str, list[str]] = {}  # comment_id → accumulated text parts

    for elem in body.iter():
        tag = elem.tag

        if tag == f"{_W}commentRangeStart":
            cid = elem.get(f"{_W}id")
            if cid and cid in comment_ids:
                active[cid] = []

        elif tag == f"{_W}t":
            text = elem.text or ""
            for cid in active:
                active[cid].append(text)

        elif tag == f"{_W}commentRangeEnd":
            cid = elem.get(f"{_W}id")
            if cid and cid in active:
                anchors[cid] = "".join(active.pop(cid)).strip()

    return anchors
