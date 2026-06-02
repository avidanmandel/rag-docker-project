#!/usr/bin/env python3
"""Delete disposable soak candidate baseline sets and session objects (dry-run by default)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from aws_storage_service import aws_storage  # noqa: E402

PRODUCTION_SET = "production"
DISPOSABLE_BASELINE_RE = re.compile(r"^candidate(?:-soak)?-[a-zA-Z0-9_-]+$")


def _session_prefix(session_id: str) -> str:
    return f"{config.normalised_s3_prefix()}sessions/{session_id.strip()}/"


def list_session_keys(session_id: str) -> list[str]:
    missing = config.validate_aws_config()
    if missing:
        return []
    aws_storage._ensure_clients()
    bucket = config.AWS_S3_BUCKET.strip()
    prefix = _session_prefix(session_id)
    keys: list[str] = []
    paginator = aws_storage._s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj.get("Key") or ""
            if key:
                keys.append(key)
    return keys


def list_baseline_keys(baseline_set_id: str) -> list[str]:
    objs = aws_storage.list_baseline_s3_objects(baseline_set_id)
    keys = [o["key"] for o in objs]
    sidecars = [aws_storage.metadata_sidecar_key(k) for k in keys]
    return keys + sidecars


def list_disposable_baseline_sets() -> list[str]:
    missing = config.validate_aws_config()
    if missing:
        return []
    aws_storage._ensure_clients()
    bucket = config.AWS_S3_BUCKET.strip()
    root = f"{config.normalised_s3_prefix()}baseline/"
    sets: set[str] = set()
    paginator = aws_storage._s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=root, Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            prefix = cp.get("Prefix") or ""
            set_id = prefix[len(root) :].strip("/")
            if set_id and set_id != PRODUCTION_SET and DISPOSABLE_BASELINE_RE.match(set_id):
                sets.add(set_id)
    return sorted(sets)


def delete_session_keys(keys: list[str]) -> int:
    if not keys:
        return 0
    missing = config.validate_aws_config()
    if missing:
        raise RuntimeError("Missing AWS configuration: " + ", ".join(missing))
    aws_storage._ensure_clients()
    bucket = config.AWS_S3_BUCKET.strip()
    objects = [{"Key": k} for k in keys]
    aws_storage._s3.delete_objects(
        Bucket=bucket,
        Delete={"Objects": objects, "Quiet": True},
    )
    return len(objects)


def delete_baseline_set(baseline_set_id: str) -> dict:
    if baseline_set_id == PRODUCTION_SET:
        raise RuntimeError("Refusing to delete production baseline set.")
    if not DISPOSABLE_BASELINE_RE.match(baseline_set_id):
        raise RuntimeError(f"Refusing to delete unrecognized baseline set: {baseline_set_id}")
    keys = [k for k in list_baseline_keys(baseline_set_id) if not k.endswith(".metadata.json")]
    if not keys:
        return {"baseline_set_id": baseline_set_id, "deleted": 0, "errors": []}

    missing = config.validate_aws_config()
    if missing:
        raise RuntimeError("Missing AWS configuration: " + ", ".join(missing))
    aws_storage._ensure_clients()
    bucket = config.AWS_S3_BUCKET.strip()
    allowed_prefix = config.baseline_s3_prefix(baseline_set_id).lower()
    objects: list[dict[str, str]] = []
    for key in keys:
        normalized = str(key or "")
        if not normalized.lower().startswith(allowed_prefix):
            raise RuntimeError("Refusing to delete object outside managed baseline prefix.")
        objects.append({"Key": normalized})
        objects.append({"Key": aws_storage.metadata_sidecar_key(normalized)})

    response = aws_storage._s3.delete_objects(
        Bucket=bucket,
        Delete={"Objects": objects, "Quiet": False},
    )
    errors = response.get("Errors") or []
    deleted = len(response.get("Deleted") or [])
    return {
        "baseline_set_id": baseline_set_id,
        "deleted": deleted,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup disposable soak baseline/session S3 objects")
    parser.add_argument("--baseline-set-id", action="append", default=[], help="Disposable baseline set to remove")
    parser.add_argument("--session-id", action="append", default=[], help="Disposable soak session UUID")
    parser.add_argument("--auto-disposable-baselines", action="store_true", help="List/delete all candidate-* sets")
    parser.add_argument("--apply", action="store_true", help="Perform deletes (default is dry-run listing)")
    args = parser.parse_args()

    baseline_sets = list(args.baseline_set_id)
    if args.auto_disposable_baselines:
        baseline_sets.extend(list_disposable_baseline_sets())
    baseline_sets = sorted(set(baseline_sets))

    report: dict = {
        "dry_run": not args.apply,
        "baseline_sets": {},
        "sessions": {},
        "baseline_key_count": 0,
        "session_key_count": 0,
    }

    for set_id in baseline_sets:
        keys = list_baseline_keys(set_id)
        report["baseline_sets"][set_id] = {"keys": len(keys)}
        report["baseline_key_count"] += len(keys)
        if args.apply and keys:
            report["baseline_sets"][set_id]["delete"] = delete_baseline_set(set_id)

    for sid in args.session_id:
        keys = list_session_keys(sid)
        report["sessions"][sid] = {"keys": len(keys)}
        report["session_key_count"] += len(keys)
        if args.apply and keys:
            delete_session_keys(keys)
            report["sessions"][sid]["deleted"] = len(keys)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
