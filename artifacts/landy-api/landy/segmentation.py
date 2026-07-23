"""Clause segmentation module.

Parses extracted contract text into clause units with:
  - ordinal: reading order index (0-based internally, 1-based in DB)
  - heading_path: e.g. "Pasal 5" or "Pasal 3 > Ayat (2)" or "3.1"
  - text: clause body text
  - char_start / char_end: character offsets into the original extracted text

Segmentation strategy (in order of priority):
  1. Pasal / Article headings (Indonesian / English contracts)
  2. Numbered items (1., 2., (1), (2)) at the top level
  3. Lettered items ((a), (b)) at the top level
  4. Paragraph fallback (split on blank lines)

Documents with no explicit structure are treated as a series of paragraphs,
each of which becomes a clause. Never produce zero clauses from a non-empty
document.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Clause:
    ordinal: int           # 1-based
    heading_path: Optional[str]
    text: str
    char_start: int
    char_end: int


# ── Heading patterns ──────────────────────────────────────────────────────────

_PASAL_RE = re.compile(
    r"^(PASAL|Pasal|ARTICLE|Article)\s+(\d+[A-Z]?)\b",
    re.MULTILINE,
)

_NUMBERED_ITEM_RE = re.compile(
    r"^(\d+)\.\s+",
    re.MULTILINE,
)

_PAREN_ITEM_RE = re.compile(
    r"^\((\d+)\)\s+",
    re.MULTILINE,
)

_LETTERED_ITEM_RE = re.compile(
    r"^\(([a-z])\)\s+",
    re.MULTILINE,
)

_DOTTED_ITEM_RE = re.compile(
    r"^(\d+\.\d+(?:\.\d+)*)\s+",
    re.MULTILINE,
)


def segment(text: str) -> list[Clause]:
    """Segment extracted contract text into clause units."""
    if not text or not text.strip():
        return []

    # Try structured segmentation in order of specificity
    for strategy in (_segment_by_pasal, _segment_by_dotted, _segment_by_numbered, _segment_by_paren):
        clauses = strategy(text)
        if clauses:
            return clauses

    # Fallback: split by blank lines → paragraphs
    return _segment_by_paragraphs(text)


# ── Strategy implementations ──────────────────────────────────────────────────

def _segment_by_pasal(text: str) -> list[Clause]:
    """Split by Pasal / Article headings."""
    matches = list(_PASAL_RE.finditer(text))
    if not matches:
        return []

    clauses: list[Clause] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        heading = f"{m.group(1)} {m.group(2)}"

        # Look for sub-items within this Pasal
        sub_clauses = _extract_sub_clauses(section_text, heading, start)
        if sub_clauses:
            clauses.extend(sub_clauses)
        else:
            clauses.append(Clause(
                ordinal=len(clauses) + 1,
                heading_path=heading,
                text=section_text,
                char_start=start,
                char_end=end,
            ))

    _renumber(clauses)
    return clauses


def _segment_by_dotted(text: str) -> list[Clause]:
    """Split by dotted numbering like 1.1, 1.2, 2.1 ..."""
    matches = list(_DOTTED_ITEM_RE.finditer(text))
    if len(matches) < 2:
        return []
    return _build_clauses_from_matches(text, matches, label_fn=lambda m: m.group(1))


def _segment_by_numbered(text: str) -> list[Clause]:
    """Split by plain numbered items: 1. 2. 3."""
    matches = list(_NUMBERED_ITEM_RE.finditer(text))
    if len(matches) < 2:
        return []
    return _build_clauses_from_matches(text, matches, label_fn=lambda m: m.group(1) + ".")


def _segment_by_paren(text: str) -> list[Clause]:
    """Split by parenthesized numbers: (1) (2) (3)."""
    matches = list(_PAREN_ITEM_RE.finditer(text))
    if len(matches) < 2:
        return []
    return _build_clauses_from_matches(text, matches, label_fn=lambda m: f"({m.group(1)})")


def _segment_by_paragraphs(text: str) -> list[Clause]:
    """Paragraph fallback: split on two or more consecutive newlines."""
    raw_paras = re.split(r"\n{2,}", text)
    clauses: list[Clause] = []
    offset = 0
    for para in raw_paras:
        stripped = para.strip()
        if not stripped:
            offset += len(para) + 2  # account for the split
            continue
        # Find where this paragraph starts in the original text
        start = text.find(stripped, offset)
        end = start + len(stripped)
        clauses.append(Clause(
            ordinal=len(clauses) + 1,
            heading_path=None,
            text=stripped,
            char_start=start,
            char_end=end,
        ))
        offset = end
    return clauses


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_sub_clauses(section_text: str, parent_heading: str, base_offset: int) -> list[Clause]:
    """Look for (1), (a) etc. inside a Pasal section."""
    for pattern, label_fn in [
        (_PAREN_ITEM_RE,   lambda m: f"({m.group(1)})"),
        (_LETTERED_ITEM_RE, lambda m: f"({m.group(1)})"),
    ]:
        matches = list(pattern.finditer(section_text))
        if len(matches) >= 2:
            clauses: list[Clause] = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
                sub_text = section_text[start:end].strip()
                clauses.append(Clause(
                    ordinal=len(clauses) + 1,
                    heading_path=f"{parent_heading} > Ayat {label_fn(m)}",
                    text=sub_text,
                    char_start=base_offset + start,
                    char_end=base_offset + end,
                ))
            return clauses
    return []


def _build_clauses_from_matches(
    text: str,
    matches: list[re.Match],
    label_fn,
) -> list[Clause]:
    clauses: list[Clause] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clause_text = text[start:end].strip()
        clauses.append(Clause(
            ordinal=i + 1,
            heading_path=label_fn(m),
            text=clause_text,
            char_start=start,
            char_end=end,
        ))
    return clauses


def _renumber(clauses: list[Clause]) -> None:
    for i, c in enumerate(clauses):
        c.ordinal = i + 1
