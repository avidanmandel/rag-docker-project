"""Remove accidental ScoutMatch-Admin-Token.txt session documents safely."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
import database  # noqa: E402
from aws_storage_service import aws_storage  # noqa: E402

TARGET_DISPLAY_NAME = "ScoutMatch-Admin-Token.txt"


def main() -> int:
    database.init_db()
    docs = database.find_session_documents_by_display_name(TARGET_DISPLAY_NAME)
    if not docs:
        print(f"No DB rows found for {TARGET_DISPLAY_NAME}")
        return 0

    session_prefix = f"{config.normalised_s3_prefix()}sessions/"
    safe_docs = []
    for doc in docs:
        key = str(doc.get("s3_key") or "")
        if not key.startswith(session_prefix):
            print(f"Skipping non-session key: {key}")
            continue
        safe_docs.append(doc)

    if not safe_docs:
        print("No session-scoped rows eligible for deletion.")
        return 1

    delete_result = aws_storage.delete_recorded_session_objects(safe_docs)
    for doc in safe_docs:
        database.delete_session_document(doc["session_id"], doc["id"])

    if delete_result.get("deleted", 0) > 0:
        ingestion = aws_storage.start_ingestion_job()
        print(
            "Deleted objects:",
            delete_result.get("deleted", 0),
            "ingestion:",
            ingestion.get("ingestion_job_id"),
        )
    else:
        print("No S3 objects deleted.")

    print(f"Removed {len(safe_docs)} DB row(s) for {TARGET_DISPLAY_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
