#!/usr/bin/env python3
"""Build a focused lecturer-facing ZIP for baseline-club-v14."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"
DEFAULT_ZIP_NAME = "Avidan_RAG_Docker_Project-lecturer-package-v14"

ROOT_FILES = (
    "README.md",
    "app.py",
    "aws_kb_engine.py",
    "aws_storage_service.py",
    "baseline_club_knowledge.py",
    "chunker.py",
    "config.py",
    "database.py",
    "requirement_verification.py",
    "rag_engine.py",
    "image_extract.py",
    "pdf_loader.py",
    "requirements.txt",
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    ".env.ec2.example",
)

DOC_FILES = (
    "docs/FINAL_QA_REPORT.md",
    "docs/PROJECT_STATE.md",
    "docs/KNOWN_LIMITATIONS.md",
    "docs/RAG_DATA_LIFECYCLE.md",
    "docs/DEPLOYMENT_RUNBOOK.md",
    "docs/SUBMISSION_CHECKLIST.md",
)

STATIC_IMAGES = (
    "static/images/home-dashboard-art.png",
    "static/images/stadium-home.png",
)

BASELINE_FILES = (
    "sample_scout_data/baseline/manifest.json",
    "sample_scout_data/baseline/club_profile.txt",
    "sample_scout_data/baseline/coach_tactical_model.txt",
    "sample_scout_data/baseline/squad_depth_chart.csv",
    "sample_scout_data/baseline/transfer_budget.txt",
    "sample_scout_data/baseline/upcoming_fixtures.csv",
    "sample_scout_data/baseline/fixture_congestion_note.txt",
    "sample_scout_data/baseline/winter_window_priorities.txt",
    "sample_scout_data/baseline/recruitment_policy.txt",
    "sample_scout_data/baseline/tactical_summary.docx",
    "sample_scout_data/baseline/winter_window_overview.pdf",
)

SAMPLE_CANDIDATES = (
    "sample_scout_data/team_requirements.txt",
    "sample_scout_data/player_cvs/forward_or_david.txt",
    "sample_scout_data/scouting_reports/forward_or_david_report.txt",
    "sample_scout_data/demo_candidates/ron_ben_ari_cv.pdf",
    "sample_scout_data/demo_candidates/dor_levi_cv.docx",
    "sample_scout_data/demo_candidates/eyal_mor_cv.csv",
)

TEST_FILES = (
    "tests/test_scoutmatch.py",
    "tests/test_baseline_club_knowledge.py",
)

EVIDENCE_FILES = (
    "submission_evidence/README.md",
)


def collect_paths() -> list[Path]:
    paths: list[Path] = []
    for rel in (
        *ROOT_FILES,
        *DOC_FILES,
        *STATIC_IMAGES,
        *BASELINE_FILES,
        *SAMPLE_CANDIDATES,
        *TEST_FILES,
        *EVIDENCE_FILES,
    ):
        path = ROOT / Path(rel)
        if not path.is_file():
            raise FileNotFoundError(f"Required lecturer file missing: {rel}")
        paths.append(path)

    for subdir in ("templates", "static/css", "static/js"):
        base = ROOT / subdir
        for file in sorted(base.rglob("*")):
            if file.is_file():
                paths.append(file)

    final_v14 = ROOT / "submission_evidence" / "final_v14"
    for png in sorted(final_v14.glob("*.png")):
        paths.append(png)

    return sorted(set(paths), key=lambda p: p.relative_to(ROOT).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--zip-name",
        default=DEFAULT_ZIP_NAME,
        help="Base filename without extension (default: lecturer-package-v14)",
    )
    args = parser.parse_args()
    zip_name = args.zip_name
    zip_path = OUT / f"{zip_name}.zip"
    manifest_path = OUT / f"{zip_name}.manifest.txt"
    sha_path = OUT / f"{zip_name}.sha256.txt"

    if zip_path.exists():
        raise SystemExit(f"Refusing to overwrite existing ZIP: {zip_path}")

    OUT.mkdir(parents=True, exist_ok=True)
    files = collect_paths()
    rel_paths = [p.relative_to(ROOT).as_posix() for p in files]

    manifest_path.write_text("\n".join(rel_paths) + "\n", encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arc in zip(files, rel_paths):
            zf.write(path, arc)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest().upper()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    print(f"lecturer_zip={zip_path.resolve()}")
    print(f"manifest={manifest_path.resolve()}")
    print(f"sha256={sha_path.resolve()}")
    print(f"file_count={len(files)}")
    print(f"sha256_hash={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
