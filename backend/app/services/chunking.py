"""Splits extracted document text into overlapping chunks for embedding.

Character-based (not token-based) — see CLAUDE.md's chunk_size_chars comment
for why. Chunking respects paragraph and sentence boundaries where possible
rather than slicing mid-sentence; only truly oversized "sentences" (e.g. a
giant unbroken blob of text) get hard-split by character count as a last
resort.

This is intentionally NOT full "structure detection" (headings, tables,
page layout) per spec §13 — it operates on the flat extracted_text Phase 4
produces. Structure-aware chunking (using page/heading metadata) is a
reasonable future enhancement once extraction preserves that structure, not
implemented now — tracked in PLAN.md, not silently skipped.
"""

import re
from dataclasses import dataclass

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    char_count: int


def chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Chunks are approximately `chunk_size` characters, with roughly
    `chunk_overlap` characters of trailing context carried into the next
    chunk. Because chunks are built from whole paragraph/sentence units (never
    split mid-sentence except as a last resort), an individual chunk can
    modestly exceed chunk_size + chunk_overlap by up to 2 characters (the
    "\\n\\n" separator inserted between carried-over overlap text and the next
    unit) — bounded, not exact.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]

    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            units.append(paragraph)
        else:
            units.extend(_split_long_paragraph(paragraph, chunk_size))

    raw_chunks = _pack_units(units, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [
        Chunk(index=i, content=content, char_count=len(content))
        for i, content in enumerate(raw_chunks)
    ]


def _pack_units(units: list[str], *, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= chunk_size or not current:
            current = candidate
        else:
            chunks.append(current)
            overlap_text = current[-chunk_overlap:] if chunk_overlap > 0 else ""
            current = f"{overlap_text}\n\n{unit}" if overlap_text else unit
    if current:
        chunks.append(current)
    return chunks


def _split_long_paragraph(paragraph: str, chunk_size: int) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= chunk_size or not current:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)

    final: list[str] = []
    for piece in pieces:
        if len(piece) <= chunk_size:
            final.append(piece)
        else:
            # Last resort: no sentence boundary short enough was found
            # (e.g. one very long run-on sentence) — hard-split by size.
            final.extend(piece[i : i + chunk_size] for i in range(0, len(piece), chunk_size))
    return final
