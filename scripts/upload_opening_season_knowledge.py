#!/usr/bin/env python3
"""Upload opening-season dataset additively to ScoutMatch Knowledge Base S3 prefix."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from aws_storage_service import aws_storage  # noqa: E402
from opening_season_workspace import DATASET_ROOT, S3_NAMESPACE, dataset_files  # noqa: E402


def _s3_key(filename: str) -> str:
    prefix = config.normalised_s3_prefix().rstrip("/")
    namespace = S3_NAMESPACE.split("scoutmatch/knowledge-base/")[-1].rstrip("/")
    return f"{prefix}/{namespace}/{filename.replace(chr(92), '/')}"


def upload(*, apply: bool, wait_sync: bool) -> dict:
    bucket = (config.AWS_S3_BUCKET or "").strip()
    if not bucket:
        return {"status": "BLOCKED", "reason": "AWS_S3_BUCKET not configured"}

    files = dataset_files()
    summary = {
        "status": "PLANNED",
        "bucket": bucket,
        "namespace": S3_NAMESPACE,
        "file_count": len(files),
        "uploaded": 0,
        "skipped": 0,
        "failed": 0,
        "keys": [],
    }
    if not files:
        summary["status"] = "BLOCKED"
        summary["reason"] = "no_dataset_files_found"
        return summary

    for path in files:
        rel = path.relative_to(DATASET_ROOT).as_posix()
        key = _s3_key(rel)
        summary["keys"].append(key)
        if not apply:
            continue
        try:
            import boto3

            bucket = config.AWS_S3_BUCKET.strip()
            boto3.client("s3", region_name=config.AWS_REGION).put_object(
                Bucket=bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType="text/plain; charset=utf-8",
            )
            summary["uploaded"] += 1
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            summary.setdefault("errors", []).append(f"{rel}: {exc}")

    if not apply:
        return summary

    if summary["failed"]:
        summary["status"] = "PARTIAL"
        return summary

    summary["status"] = "UPLOADED"
    if wait_sync:
        try:
            job = aws_storage.start_ingestion_job(wait_for_complete=True)
            summary["ingestion"] = {
                "ingestion_job_id": job.get("ingestion_job_id"),
                "status": job.get("status"),
            }
            summary["ingestion_status"] = job.get("status")
        except Exception as exc:  # noqa: BLE001
            summary["ingestion_status"] = "BLOCKED"
            summary["ingestion_error"] = str(exc)
    else:
        try:
            job = aws_storage.start_ingestion_job(wait_for_complete=False)
            summary["ingestion"] = job
            summary["ingestion_status"] = job.get("status", "STARTED")
        except Exception as exc:  # noqa: BLE001
            summary["ingestion_status"] = "BLOCKED"
            summary["ingestion_error"] = str(exc)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Upload files to S3")
    parser.add_argument("--wait-sync", action="store_true", help="Wait for KB ingestion")
    args = parser.parse_args()
    result = upload(apply=args.apply, wait_sync=args.wait_sync)
    print(json.dumps(result, indent=2))
    if result.get("status") in {"BLOCKED", "PARTIAL"}:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
