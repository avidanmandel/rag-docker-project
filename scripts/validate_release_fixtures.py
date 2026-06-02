#!/usr/bin/env python3
"""Validate release fixture formats (TXT, PDF, DOCX, CSV) via production upload parsers."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import _parse_upload_player_facts  # noqa: E402

BLOCKERS: list[str] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"RESULT {name}={status}{(': ' + detail) if detail else ''}")
    if not ok:
        BLOCKERS.append(f"{name}: {detail or status}")


def player_cv(name: str, position: str, salary: int, relocation: str, availability: str) -> str:
    rel = "YES" if relocation.lower().startswith("y") else "NO"
    return (
        f"Full Name: {name} | Position: {position}\n"
        f"Annual Salary Expectation: {salary:,} EUR\n"
        f"Relocation Willingness: {rel}\n"
        f"Availability: {availability}\n"
    )


def csv_player(name: str, position: str, salary: int, relocation: str, availability: str) -> str:
    rel = "YES" if relocation.lower().startswith("y") else "NO"
    return (
        "field,value\n"
        f"Full Name,{name}\n"
        f"Position,{position}\n"
        f"Annual Salary Expectation,{salary} EUR\n"
        f"Relocation Willingness,{rel}\n"
        f"Availability,{availability}\n"
    )


def make_pdf(text: str) -> bytes:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "flvm",
        ROOT / "scripts" / "full_live_validation_matrix.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.make_pdf(text)


def make_docx(text: str) -> bytes:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def main() -> int:
    fixtures = [
        ("txt", ".txt", player_cv("Or David", "Forward", 58000, "yes", "January 2026").encode()),
        ("csv", ".csv", csv_player("Amit Levy", "Defender", 58000, "yes", "July 2025").encode()),
        ("pdf", ".pdf", make_pdf(player_cv("Luca Romano", "Defender", 55000, "yes", "immediate"))),
        ("docx", ".docx", make_docx(player_cv("Noam David", "Defender", 52000, "no", "immediate"))),
    ]
    for label, ext, raw in fixtures:
        parsed = _parse_upload_player_facts(raw, ext)
        ok = bool(parsed.get("parsed_player_name")) and parsed.get("parsed_salary_eur") is not None
        if label == "csv":
            ok = ok and parsed.get("parsed_relocation") == "YES" and parsed.get("parsed_position") == "Defender"
        record(f"fixture_{label}", ok, str(parsed))

    print("BLOCKERS", len(BLOCKERS))
    for blocker in BLOCKERS:
        print("BLOCKER", blocker)
    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    raise SystemExit(main())
