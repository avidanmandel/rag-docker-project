"""
PDF text extraction using pypdf.

Each PDF page is returned as a (filename, page_number, text) tuple so chunks
keep a meaningful citation back to the source slide/page.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pypdf import PdfReader


def _clean(text: str) -> str:
    """Light cleanup: collapse repeated whitespace, drop stray form-feeds."""
    text = text.replace("\x0c", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def load_pdf(path: Path) -> list[tuple[str, int, str]]:
    """Return a list of (filename, page_number_1_based, page_text) entries."""
    reader = PdfReader(str(path))
    out: list[tuple[str, int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        text = _clean(raw)
        if text:
            out.append((path.name, i, text))
    return out


def load_folder(folder: Path) -> list[tuple[str, int, str]]:
    """Load every .pdf and .txt under `folder`. .txt files become page 1."""
    if not folder.exists():
        raise FileNotFoundError(f"Knowledge base folder not found: {folder}")

    entries: list[tuple[str, int, str]] = []
    for file_name in sorted(os.listdir(folder)):
        path = folder / file_name
        if not path.is_file():
            continue

        lower = file_name.lower()
        if lower.endswith(".pdf"):
            entries.extend(load_pdf(path))
        elif lower.endswith(".txt"):
            text = _clean(path.read_text(encoding="utf-8", errors="ignore"))
            if text:
                entries.append((file_name, 1, text))

    if not entries:
        raise ValueError(
            f"No readable PDF or TXT files found in '{folder}'."
        )
    return entries
