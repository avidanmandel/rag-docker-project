#!/usr/bin/env python3
"""Read-only audit of baseline club knowledge registry vs S3."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import database  # noqa: E402
from aws_storage_service import aws_storage  # noqa: E402

BASELINE_DIR = ROOT / "sample_scout_data" / "baseline"


def audit(*, baseline_set_id: str | None) -> dict:
    set_id = (baseline_set_id or config.AWS_BASELINE_SET_ID).strip()
    database.init_db()
    issues: list[str] = []
    db_rows = {row["s3_key"]: row for row in database.list_baseline_documents(set_id)}
    s3_objects = {obj["key"]: obj for obj in aws_storage.list_baseline_s3_objects(set_id)}

    for key, row in db_rows.items():
        if key not in s3_objects:
            issues.append(f"missing_source:{key}")
        meta = aws_storage.read_metadata_sidecar(key)
        if not meta:
            issues.append(f"missing_sidecar:{key}")
        elif meta.get("scope") != "baseline":
            issues.append(f"invalid_scope:{key}")
        elif meta.get("baseline_set_id") != set_id:
            issues.append(f"invalid_baseline_set_id:{key}")
        expected_hash = row.get("content_hash")
        if expected_hash and key in s3_objects:
            try:
                body = aws_storage.read_object_bytes(key)
                actual = hashlib.sha256(body).hexdigest()
                if actual != expected_hash:
                    issues.append(f"hash_mismatch:{key}")
            except Exception:
                issues.append(f"read_failed:{key}")

    for key in s3_objects:
        if key not in db_rows:
            issues.append(f"orphan_source:{key}")
        sidecar_key = aws_storage.metadata_sidecar_key(key)
        if sidecar_key not in {aws_storage.metadata_sidecar_key(k) for k in s3_objects}:
            issues.append(f"missing_sidecar_for_source:{key}")

    manifest_path = BASELINE_DIR / "manifest.json"
    manifest_count = 0
    if manifest_path.is_file():
        manifest_count = len(json.loads(manifest_path.read_text(encoding="utf-8")).get("files") or [])

    return {
        "baseline_set_id": set_id,
        "manifest_files": manifest_count,
        "db_rows": len(db_rows),
        "s3_sources": len(s3_objects),
        "issues": issues,
        "clean": not issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit baseline club knowledge")
    parser.add_argument("--baseline-set-id", default=None)
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    result = audit(baseline_set_id=args.baseline_set_id)
    print(json.dumps(result, indent=2))
    if not result["clean"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
