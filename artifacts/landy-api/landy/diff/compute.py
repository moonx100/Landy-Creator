"""Clause-level diff computation between two document versions.

Uses Python difflib.SequenceMatcher to align clause sequences and produce
a list of DiffEntry objects — one per changed clause pair.

Matching strategy:
  - Clauses are matched in ordinal order using full-text similarity.
  - SequenceMatcher identifies equal / insert / delete / replace blocks.
  - 'replace' blocks are paired by position (first-old with first-new),
    with any excess on either side treated as pure add/remove.
  - Entries with identical stripped text are silently skipped.

The diff uses the *original* (non-redacted) clause text — redaction is an
LLM pre-processing step and must not affect what the user sees in the diff.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Optional


@dataclass
class DiffEntry:
    """One changed clause pair from a version diff."""
    change_kind: str            # 'added' | 'removed' | 'modified'
    clause_ref: Optional[str]   # heading_path or "Klausul N"
    before_text: Optional[str]  # None for 'added'
    after_text: Optional[str]   # None for 'removed'


def _clause_ref(clause: dict) -> str:
    """Return a human-readable reference for a clause."""
    hp = clause.get("heading_path")
    if hp:
        return hp
    return f"Klausul {clause['ordinal']}"


def compute_clause_diff(
    old_clauses: list[dict],  # [{id, ordinal, heading_path, text}, ...]
    new_clauses: list[dict],
) -> list[DiffEntry]:
    """Diff two ordered clause lists and return only the changed entries.

    Args:
        old_clauses: Clauses from the prior version, ordered by ordinal.
        new_clauses: Clauses from the new version, ordered by ordinal.

    Returns:
        List of DiffEntry objects, one per changed clause (or clause pair).
        Empty if the versions are textually identical.
    """
    old_texts = [c["text"] for c in old_clauses]
    new_texts = [c["text"] for c in new_clauses]

    # autojunk=False — contract clauses are never "junk" regardless of frequency
    matcher = difflib.SequenceMatcher(None, old_texts, new_texts, autojunk=False)

    entries: list[DiffEntry] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        elif tag == "insert":
            # Clauses present in new version that have no counterpart in old
            for j in range(j1, j2):
                nc = new_clauses[j]
                entries.append(
                    DiffEntry(
                        change_kind="added",
                        clause_ref=_clause_ref(nc),
                        before_text=None,
                        after_text=nc["text"],
                    )
                )

        elif tag == "delete":
            # Clauses present in old version that were removed in new
            for i in range(i1, i2):
                oc = old_clauses[i]
                entries.append(
                    DiffEntry(
                        change_kind="removed",
                        clause_ref=_clause_ref(oc),
                        before_text=oc["text"],
                        after_text=None,
                    )
                )

        elif tag == "replace":
            # Block of old clauses replaced by a block of new clauses.
            # Pair by position up to the shorter block; remainder are
            # pure adds/removes.
            old_block = old_clauses[i1:i2]
            new_block = new_clauses[j1:j2]
            paired = min(len(old_block), len(new_block))

            for k in range(paired):
                oc, nc = old_block[k], new_block[k]
                # Skip if only whitespace differs
                if oc["text"].strip() == nc["text"].strip():
                    continue
                entries.append(
                    DiffEntry(
                        change_kind="modified",
                        clause_ref=_clause_ref(nc) or _clause_ref(oc),
                        before_text=oc["text"],
                        after_text=nc["text"],
                    )
                )

            # Unpaired old clauses → removed
            for k in range(paired, len(old_block)):
                oc = old_block[k]
                entries.append(
                    DiffEntry(
                        change_kind="removed",
                        clause_ref=_clause_ref(oc),
                        before_text=oc["text"],
                        after_text=None,
                    )
                )

            # Unpaired new clauses → added
            for k in range(paired, len(new_block)):
                nc = new_block[k]
                entries.append(
                    DiffEntry(
                        change_kind="added",
                        clause_ref=_clause_ref(nc),
                        before_text=None,
                        after_text=nc["text"],
                    )
                )

    return entries
