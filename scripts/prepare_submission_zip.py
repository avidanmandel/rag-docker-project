#!/usr/bin/env python3
"""Build clean submission ZIP with manifest and SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"

EXCLUDE_DIR_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".aws", "artifacts", "runtime", "dist",
    ".pytest_cache", "screenshoot",
}
EXCLUDE_FILE_GLOBS = ("*.pem", "*.key", "*.log", "chat.db", "*.db", "*.bak", ".env")
EXCLUDE_PATH_RE = re.compile(
    r"(^|/)(home-preview-|submission_evidence/archive|docs/archive|tests/escape\.txt|"
    r"static/images/(design-reference|home-dashboard-panel|player-home|sir-alex-home)\.png|"
    r"scripts/(audit_|deploy_session_docs_v[3-7]|validate_candidate|validate_prod|validate_public|"
    r"candidate_|cutover_session_docs_v[34])|rollback/)"
)


def should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith("dist/"):
        return False
    parts = rel.split("/")
    if any(p in EXCLUDE_DIR_PARTS for p in parts):
        return False
    if path.name.startswith(".env"):
        return path.name in (".env.example", ".env.ec2.example")
    for pat in EXCLUDE_FILE_GLOBS:
        if path.match(pat):
            return False
    if EXCLUDE_PATH_RE.search(rel):
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-cleanup", action="store_true")
    args = parser.parse_args()
    suffix = "-pre-cleanup" if args.pre_cleanup else ""
    zip_path = OUT / f"Avidan_RAG_Docker_Project-submission{suffix}.zip"
    manifest_path = OUT / f"Avidan_RAG_Docker_Project-submission{suffix}.manifest.txt"
    sha_path = OUT / f"Avidan_RAG_Docker_Project-submission{suffix}.sha256.txt"

    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and should_include(p))
    rel_paths = [p.relative_to(ROOT).as_posix() for p in files]
    manifest_path.write_text("\n".join(rel_paths) + "\n", encoding="utf-8")

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arc in zip(files, rel_paths):
            zf.write(path, arc)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest().upper()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    print(f"submission_zip={zip_path}")
    print(f"manifest={manifest_path}")
    print(f"sha256={sha_path}")
    print(f"file_count={len(files)}")
    print(f"sha256_hash={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
