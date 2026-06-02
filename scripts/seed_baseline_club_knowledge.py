#!/usr/bin/env python3
"""Seed managed baseline club knowledge to S3 (dry-run by default)."""

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
from baseline_club_knowledge import parse_baseline_file_content  # noqa: E402

BASELINE_DIR = ROOT / "sample_scout_data" / "baseline"


def _load_manifest() -> dict:
    path = BASELINE_DIR / "manifest.json"
    if not path.is_file():
        raise SystemExit(f"Missing manifest: {path}. Run generate_baseline_club_knowledge.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _file_bytes(name: str) -> bytes:
    path = BASELINE_DIR / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path.read_bytes()


def seed(*, apply: bool, baseline_set_id: str | None, wait_sync: bool) -> dict:
    set_id = (baseline_set_id or config.AWS_BASELINE_SET_ID).strip()
    manifest = _load_manifest()
    summary = {
        "baseline_set_id": set_id,
        "dry_run": not apply,
        "uploaded": 0,
        "skipped": 0,
        "updated": 0,
        "failed": 0,
    }

    database.init_db()
    existing = {
        row["s3_key"]: row
        for row in database.list_baseline_documents(set_id)
    }

    for entry in manifest.get("files") or []:
        filename = entry["filename"]
        try:
            raw = _file_bytes(filename)
        except FileNotFoundError:
            summary["failed"] += 1
            continue
        digest = hashlib.sha256(raw).hexdigest()
        key = aws_storage.build_baseline_object_key(filename, baseline_set_id=set_id)
        prior = existing.get(key)
        if prior and prior.get("content_hash") == digest:
            summary["skipped"] += 1
            continue
        if not apply:
            summary["uploaded"] += 1
            continue
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        parsed = parse_baseline_file_content(text, filename) if text else {}
        result = aws_storage.upload_baseline_document(
            raw,
            filename,
            baseline_set_id=set_id,
            category=entry.get("category"),
            content_hash=digest,
        )
        database.upsert_baseline_document(
            set_id,
            result["key"],
            result["display_name"],
            category=entry.get("category"),
            content_hash=digest,
            parsed_facts=parsed,
        )
        if prior:
            summary["updated"] += 1
        else:
            summary["uploaded"] += 1

    if apply and wait_sync and (summary["uploaded"] or summary["updated"]):
        database.set_baseline_sync_state(set_id, sync_state=config.BASELINE_SYNC_STATE_SYNCING)
        try:
            job = aws_storage.sync_knowledge_base()
            status = job.get("status") or "UNKNOWN"
            if status == "COMPLETE":
                database.set_baseline_sync_state(
                    set_id,
                    sync_state=config.BASELINE_SYNC_STATE_READY,
                    last_job_id=job.get("ingestion_job_id"),
                )
            else:
                database.set_baseline_sync_state(
                    set_id,
                    sync_state=config.BASELINE_SYNC_STATE_ERROR,
                    last_job_id=job.get("ingestion_job_id"),
                )
        except Exception:
            database.set_baseline_sync_state(set_id, sync_state=config.BASELINE_SYNC_STATE_ERROR)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed baseline club knowledge to S3")
    parser.add_argument("--apply", action="store_true", help="Upload to S3 (default is dry-run)")
    parser.add_argument("--baseline-set-id", default=None)
    parser.add_argument("--no-sync", action="store_true", help="Skip Bedrock ingestion wait")
    args = parser.parse_args()

    if not config.BASELINE_KNOWLEDGE_ENABLED and args.apply:
        print("Warning: BASELINE_KNOWLEDGE_ENABLED is false in environment.")

    summary = seed(
        apply=args.apply,
        baseline_set_id=args.baseline_set_id,
        wait_sync=not args.no_sync,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
