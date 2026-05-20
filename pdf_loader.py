"""
PDF text extraction using pypdf.

Each PDF page is returned as a (filename, page_number, text) tuple so chunks
keep a meaningful citation back to the source slide/page.
"""

from __future__ import annotations

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
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        print(f"[pdf_loader] Skipping '{path.name}': {exc}", flush=True)
        return []
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
    """Load every .pdf and .txt under ``folder`` (recursive). .txt → page 1."""
    if not folder.exists():
        raise FileNotFoundError(f"Knowledge base folder not found: {folder}")

    entries: list[tuple[str, int, str]] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue

        rel_name = path.relative_to(folder).as_posix()
        lower = rel_name.lower()
        if lower.endswith(".pdf"):
            for _, page, text in load_pdf(path):
                entries.append((rel_name, page, text))
        elif lower.endswith(".txt"):
            text = _clean(path.read_text(encoding="utf-8", errors="ignore"))
            if text:
                entries.append((rel_name, 1, text))

    return entries
