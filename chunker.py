"""
Character-window chunker with overlap.

Lecture slides and AWS/Docker docs contain dense, short paragraphs. Sentence-
level chunks lose too much context, full pages are too coarse for retrieval.
A ~700 char window with ~120 char overlap is a good middle ground.

Each chunk also remembers which file + page it came from so the UI can show
proper citations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    page: int

    def as_dict(self) -> dict:
        return {"text": self.text, "source": self.source, "page": self.page}


def _split_window(text: str, size: int, overlap: int) -> list[str]:
    """Plain sliding window over characters, trying to break at whitespace."""
    if size <= 0:
        raise ValueError("chunk size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    step = size - overlap
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            window = text[i:end]
            cut = max(window.rfind("\n"), window.rfind(". "), window.rfind(" "))
            if cut > size * 0.5:
                end = i + cut + 1
        piece = text[i:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return chunks


def chunk_pages(
    pages: list[tuple[str, int, str]],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Turn a list of (filename, page, text) tuples into Chunk objects."""
    chunks: list[Chunk] = []
    for source, page, text in pages:
        for piece in _split_window(text, chunk_size, chunk_overlap):
            chunks.append(Chunk(text=piece, source=source, page=page))
    return chunks
