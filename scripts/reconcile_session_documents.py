#!/usr/bin/env python3
"""
Read-only reconciliation audit for ScoutMatch session documents.

Compares SQLite session_documents rows against session-scoped S3 objects
and metadata sidecars. Never prints secrets or document contents.

Usage:
  python scripts/reconcile_session_documents.py --dry-run
  python scripts/reconcile_session_documents.py --session-id <id> --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from aws_storage_service import AWSStorageService  # noqa: E402


def _load_db_rows(session_id: str | None) -> list[dict]:
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    if session_id:
        rows = conn.execute(
            "SELECT id, session_id, s3_key, display_name, content_hash FROM session_documents "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, session_id, s3_key, display_name, content_hash FROM session_documents"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _list_s3_session_objects(svc: AWSStorageService, session_id: str) -> dict[str, set[str]]:
    prefix = f"{config.normalised_s3_prefix()}sessions/{session_id}/"
    bucket = config.AWS_S3_BUCKET.strip()
    svc._ensure_clients()
    sources: set[str] = set()
    sidecars: set[str] = set()
    paginator = svc._s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj.get("Key") or ""
            if not key or key.endswith("/"):
                continue
            if key.endswith(".metadata.json"):
                sidecars.add(key)
            else:
                sources.add(key)
    return {"sources": sources, "sidecars": sidecars}


def reconcile(*, session_id: str | None, dry_run: bool) -> dict:
    svc = AWSStorageService()
    rows = _load_db_rows(session_id)
    session_ids = {session_id} if session_id else {r["session_id"] for r in rows}

    categories: Counter = Counter()
    hash_dupes: Counter = Counter()
    name_dupes: Counter = Counter()

    for sid in sorted(session_ids):
        session_rows = [r for r in rows if r["session_id"] == sid]
        try:
            s3 = _list_s3_session_objects(svc, sid)
        except Exception as exc:
            print(f"session={sid} s3_list_error={exc.__class__.__name__}")
            categories["s3_list_error"] += 1
            continue

        db_keys = {r["s3_key"] for r in session_rows}
        s3_sources = s3["sources"]
        s3_sidecars = s3["sidecars"]

        for row in session_rows:
            key = row["s3_key"]
            sidecar = svc.metadata_sidecar_key(key)
            if not key.startswith(f"{config.normalised_s3_prefix()}sessions/{sid}/"):
                categories["invalid_session_prefix"] += 1
                print(f"invalid_prefix session={sid} key={key[:80]}")
            elif key in s3_sources and sidecar in s3_sidecars:
                categories["complete"] += 1
            elif key in s3_sources and sidecar not in s3_sidecars:
                categories["sidecar_missing"] += 1
                print(f"sidecar_missing session={sid} key={Path(key).name}")
            elif key not in s3_sources:
                categories["db_row_source_missing"] += 1
                print(f"db_row_source_missing session={sid} key={Path(key).name}")

        for key in s3_sources:
            if key not in db_keys:
                categories["source_missing_db_row"] += 1
                print(f"orphan_source session={sid} key={Path(key).name}")

        for sidecar in s3_sidecars:
            source = sidecar[: -len(".metadata.json")]
            if source not in s3_sources:
                categories["orphan_sidecar"] += 1
                print(f"orphan_sidecar session={sid} sidecar={Path(sidecar).name}")

        by_name: defaultdict[str, list] = defaultdict(list)
        by_hash: defaultdict[str, list] = defaultdict(list)
        for row in session_rows:
            by_name[row["display_name"]].append(row)
            if row.get("content_hash"):
                by_hash[row["content_hash"]].append(row)
        for name, group in by_name.items():
            if len(group) > 1:
                name_dupes[name] += len(group) - 1
                categories["duplicate_filename"] += len(group) - 1
        for h, group in by_hash.items():
            if len(group) > 1:
                hash_dupes[h[:8]] += len(group) - 1
                categories["duplicate_content_hash"] += len(group) - 1

    legacy_prefix = f"{config.normalised_s3_prefix()}player_cvs/"
    for row in rows:
        if legacy_prefix in row["s3_key"] and "/sessions/" not in row["s3_key"]:
            categories["legacy_global_db_row"] += 1

    print("\n--- summary ---")
    for cat, count in sorted(categories.items()):
        print(f"{cat}: {count}")
    if name_dupes:
        print(f"duplicate_filenames: {sum(name_dupes.values())}")
    if hash_dupes:
        print(f"duplicate_content_hashes: {sum(hash_dupes.values())}")
    print(f"dry_run={dry_run}")
    return dict(categories)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile ScoutMatch session documents")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true", help="Reserved; audit is read-only")
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()
    if args.apply:
        print("Note: --apply is not implemented; this script is read-only.")
    reconcile(session_id=args.session_id, dry_run=not args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
