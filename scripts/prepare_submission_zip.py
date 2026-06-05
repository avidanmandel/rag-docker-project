#!/usr/bin/env python3
"""Build clean submission ZIP with manifest, SHA-256, and forbidden-file validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"
MANIFEST_DOC = ROOT / "docs" / "SCOUTMATCH_SUBMISSION_ZIP_MANIFEST.md"

sys.path.insert(0, str(ROOT / "scripts"))
from submission_zip_rules import find_forbidden_zip_entries, should_include  # noqa: E402


def _top_level_folders(rel_paths: list[str]) -> list[str]:
    tops = sorted({p.split("/")[0] for p in rel_paths if p})
    return tops


def _secret_scan_status() -> str:
    script = ROOT / "scripts" / "run_secret_scan.py"
    if not script.exists():
        return "NOT_RUN"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
        return str(payload.get("status") or "UNKNOWN")
    except json.JSONDecodeError:
        return "REVIEW" if proc.returncode != 0 else "PASS"


def _write_manifest_doc(
    *,
    zip_name: str,
    file_count: int,
    rel_paths: list[str],
    sha256: str,
    forbidden: list[str],
    secret_scan: str,
) -> None:
    tops = _top_level_folders(rel_paths)
    status = "READY_FOR_MANUAL_SCREENSHOTS" if not forbidden else "BLOCKED_FORBIDDEN_FILES"
    lines = [
        "# ScoutMatch Submission ZIP Manifest",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Branch:** `feature/scoutmatch-agent-flow-extension`",
        f"**ZIP file:** `dist/{zip_name}`",
        f"**Status:** **{status}**",
        "",
        "## Summary",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| Total packaged files | {file_count} |",
        f"| SHA256 | `{sha256}` |",
        f"| Secret scan | {secret_scan} |",
        f"| Forbidden entries found | {len(forbidden)} |",
        "",
        "## Included top-level folders",
        "",
    ]
    for entry in tops:
        label = f"{entry}/" if any(p.startswith(f"{entry}/") for p in rel_paths) else entry
        lines.append(f"- `{label}`")
    lines.extend(
        [
            "",
            "## Exclusion confirmations",
            "",
            "| Rule | Confirmed |",
            "|------|-----------|",
            f"| `.local` directories excluded | {'yes' if not any('/.local/' in p or p.startswith('.local/') for p in rel_paths) else '**NO**'} |",
            f"| `.env` / `.env.agent` excluded | {'yes' if not any(p.endswith('.env') or p.endswith('.env.agent') for p in rel_paths) else '**NO**'} |",
            f"| PEM files excluded | {'yes' if not any(p.endswith('.pem') for p in rel_paths) else '**NO**'} |",
            f"| Repair helpers excluded | {'yes' if not any('fix_agent_model.py' in p or 'repair_agent_runtime.py' in p for p in rel_paths) else '**NO**'} |",
            f"| Runtime databases excluded | {'yes' if not any(p.endswith('chat.db') or p.endswith('.sqlite') for p in rel_paths) else '**NO**'} |",
            f"| `artifacts/` runtime evidence excluded | {'yes' if not any(p.startswith('artifacts/') for p in rel_paths) else '**NO**'} |",
            f"| Secret scan reports excluded | {'yes' if not any('secret_scan_report.json' in p for p in rel_paths) else '**NO**'} |",
            f"| `__pycache__` / `.pytest_cache` excluded | {'yes' if not any('__pycache__' in p or '.pytest_cache' in p for p in rel_paths) else '**NO**'} |",
            "",
            "## Notes",
            "",
            "- Example environment files (`.env.example`, `.env.ec2.example`) may be included with placeholders only.",
            "- SNS is optional and not required in the submission package.",
            "- Mark ZIP **FINAL** only after manual screenshots in `submission_evidence/agent_flow_extension/` are complete.",
            "",
        ]
    )
    if forbidden:
        lines.append("## Forbidden entries detected (packaging blocked)")
        lines.append("")
        for entry in forbidden:
            lines.append(f"- `{entry}`")
    MANIFEST_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_submission_zip(*, pre_cleanup: bool = False) -> int:
    suffix = "-pre-cleanup" if pre_cleanup else ""
    zip_path = OUT / f"Avidan_RAG_Docker_Project-submission{suffix}.zip"
    manifest_path = OUT / f"Avidan_RAG_Docker_Project-submission{suffix}.manifest.txt"
    sha_path = OUT / f"Avidan_RAG_Docker_Project-submission{suffix}.sha256.txt"

    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and should_include(p, root=ROOT))
    rel_paths = [p.relative_to(ROOT).as_posix() for p in files]
    manifest_path.write_text("\n".join(rel_paths) + "\n", encoding="utf-8")

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arc in zip(files, rel_paths):
            zf.write(path, arc)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_entries = zf.namelist()
    forbidden = find_forbidden_zip_entries(zip_entries)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest().upper()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    secret_scan = _secret_scan_status()
    _write_manifest_doc(
        zip_name=zip_path.name,
        file_count=len(rel_paths),
        rel_paths=rel_paths,
        sha256=digest,
        forbidden=forbidden,
        secret_scan=secret_scan,
    )

    print(f"submission_zip={zip_path}")
    print(f"manifest={manifest_path}")
    print(f"manifest_doc={MANIFEST_DOC}")
    print(f"sha256={sha_path}")
    print(f"file_count={len(rel_paths)}")
    print(f"sha256_hash={digest}")
    print(f"top_level_folders={','.join(_top_level_folders(rel_paths))}")
    print(f"forbidden_count={len(forbidden)}")
    print(f"zip_status={'BLOCKED' if forbidden else 'READY_FOR_MANUAL_SCREENSHOTS'}")
    if forbidden:
        print("forbidden_entries=" + json.dumps(forbidden))
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-cleanup", action="store_true")
    args = parser.parse_args(argv)
    return build_submission_zip(pre_cleanup=args.pre_cleanup)


if __name__ == "__main__":
    raise SystemExit(main())
