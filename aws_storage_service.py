"""
AWS storage and Knowledge Base ingestion for ScoutMatch AI.

Handles S3 uploads under the configured ScoutMatch prefix and Bedrock
Knowledge Base sync jobs via bedrock-agent.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from werkzeug.utils import secure_filename

import config

logger = logging.getLogger(__name__)

INGESTION_STATUSES = frozenset({
    "STARTING", "IN_PROGRESS", "COMPLETE", "FAILED", "STOPPING", "STOPPED",
})

_TIMESTAMP_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}$")


def canonical_display_filename(filename: str) -> str:
    """Collapse timestamped upload suffixes for sidebar display."""
    path = Path(filename)
    stem = _TIMESTAMP_SUFFIX_RE.sub("", path.stem)
    return stem + path.suffix.lower()


def _document_display_preference(doc: dict, canonical_name: str) -> tuple[int, str]:
    raw_name = (
        doc.get("display_name")
        or doc.get("display_source")
        or Path(doc.get("key") or doc.get("name") or "").name
    )
    raw_lower = raw_name.lower()
    canonical_lower = canonical_name.lower()
    if raw_lower == canonical_lower:
        rank = 3
    elif _TIMESTAMP_SUFFIX_RE.search(Path(raw_name).stem):
        rank = 1
    else:
        rank = 2
    return (rank, doc.get("last_modified") or "")


def deduplicate_documents_for_display(
    docs: list[dict],
) -> tuple[list[dict], int]:
    """Group timestamped duplicates; keep one display row per canonical file."""
    raw_count = len(docs)
    grouped: dict[tuple[str, str], dict] = {}

    for doc in docs:
        raw_name = (
            doc.get("display_name")
            or doc.get("display_source")
            or Path(doc.get("key") or doc.get("name") or "").name
        )
        category = str(doc.get("category") or "")
        canonical = canonical_display_filename(raw_name)
        group_key = (category, canonical)

        display_doc = dict(doc)
        display_doc["display_name"] = canonical
        display_doc["display_source"] = canonical
        display_doc["canonical_name"] = canonical

        existing = grouped.get(group_key)
        if (
            existing is None
            or _document_display_preference(display_doc, canonical)
            > _document_display_preference(existing, canonical)
        ):
            grouped[group_key] = display_doc

    display_docs = sorted(
        grouped.values(),
        key=lambda item: str(item.get("display_name", "")).lower(),
    )
    return display_docs, raw_count


class UploadValidationError(ValueError):
    """Raised when an upload fails validation."""


class AWSStorageService:
    """S3 document storage and Bedrock KB ingestion for ScoutMatch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_ingestion_job: dict | None = None
        self._s3: Any = None
        self._bedrock_agent: Any = None

    def _ensure_clients(self) -> None:
        if self._s3 is None:
            self._s3 = boto3.client("s3", region_name=config.AWS_REGION)
        if self._bedrock_agent is None:
            self._bedrock_agent = boto3.client(
                "bedrock-agent", region_name=config.AWS_REGION
            )

    def validate_upload(
        self,
        filename: str,
        file_size: int,
        *,
        allow_json: bool = False,
    ) -> tuple[str, str]:
        """
        Validate filename and size.

        Returns (safe_filename, extension).
        """
        if not filename or not filename.strip():
            raise UploadValidationError("No file selected.")

        safe = secure_filename(filename)
        if not safe or safe in {".", ".."}:
            raise UploadValidationError("Invalid filename.")

        if ".." in filename or filename.startswith("/") or "\\" in filename:
            raise UploadValidationError("Path traversal in filename is not allowed.")

        ext = Path(safe).suffix.lower()
        allowed = set(config.DOC_UPLOAD_EXTENSIONS)
        if allow_json:
            allowed.add(".json")

        if ext not in allowed:
            human = ", ".join(sorted(allowed))
            raise UploadValidationError(
                f"Unsupported file type '{ext}'. Allowed: {human}."
            )

        if file_size <= 0:
            raise UploadValidationError("Empty files cannot be uploaded.")

        if file_size > config.MAX_UPLOAD_BYTES:
            raise UploadValidationError(
                f"File is too large ({file_size // 1024} KB). "
                f"Maximum is {config.MAX_UPLOAD_MB} MB."
            )

        return safe, ext

    def categorise_key(self, filename: str) -> str:
        """Choose S3 subfolder based on filename patterns."""
        lower = filename.lower()
        if "team_requirement" in lower or "requirements" in lower:
            return "team_requirements"
        if "scout" in lower or "report" in lower:
            return "scouting_reports"
        return "player_cvs"

    def build_object_key(self, filename: str, *, subfolder: str | None = None) -> str:
        prefix = config.normalised_s3_prefix()
        folder = subfolder or self.categorise_key(filename)
        return f"{prefix}{folder}/{filename}"

    def object_exists(self, key: str) -> bool:
        self._ensure_clients()
        bucket = config.AWS_S3_BUCKET.strip()
        try:
            self._s3.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound", "403"):
                return False
            raise
        except Exception:
            return False

    def resolve_unique_key(self, base_key: str) -> str:
        """Append timestamp suffix if object already exists."""
        if not self.object_exists(base_key):
            return base_key
        path = Path(base_key)
        stem = path.stem
        suffix = path.suffix
        parent = path.parent.as_posix()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_name = f"{stem}_{ts}{suffix}"
        if parent and parent != ".":
            return f"{parent}/{unique_name}"
        return unique_name

    def normalise_json_to_txt(self, raw_bytes: bytes, original_name: str) -> tuple[bytes, str]:
        """Validate JSON and convert to UTF-8 text for S3."""
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UploadValidationError(
                "Invalid JSON file. Upload a valid JSON document or use TXT/PDF."
            ) from exc
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        txt_name = Path(original_name).stem + ".txt"
        return text.encode("utf-8"), txt_name

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str | None = None,
        *,
        subfolder: str | None = None,
    ) -> dict:
        """Upload file bytes to S3 under the ScoutMatch prefix."""
        missing = config.validate_aws_config()
        if missing:
            raise RuntimeError(
                "Missing AWS configuration: " + ", ".join(missing)
            )

        safe, ext = self.validate_upload(filename, len(data))
        key = self.build_object_key(safe, subfolder=subfolder)
        key = self.resolve_unique_key(key)

        self._ensure_clients()
        bucket = config.AWS_S3_BUCKET.strip()
        extra: dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type

        try:
            self._s3.put_object(Bucket=bucket, Key=key, Body=data, **extra)
        except (ClientError, BotoCoreError) as exc:
            logger.error("S3 upload failed for key=%s: %s", key, exc.__class__.__name__)
            raise RuntimeError(
                "Failed to upload document to Amazon S3. Check IAM permissions and bucket name."
            ) from exc

        return {
            "key": key,
            "filename": Path(key).name,
            "display_name": Path(key).name,
            "size": len(data),
            "extension": ext.lstrip("."),
            "s3_uri": f"s3://{bucket}/{key}",
        }

    def start_ingestion_job(self) -> dict:
        """Start a Bedrock Knowledge Base ingestion job."""
        missing = config.validate_aws_config()
        if missing:
            raise RuntimeError(
                "Missing AWS configuration: " + ", ".join(missing)
            )

        self._ensure_clients()
        kb_id = config.BEDROCK_KB_ID.strip()
        ds_id = config.BEDROCK_DATA_SOURCE_ID.strip()

        try:
            response = self._bedrock_agent.start_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                clientToken=str(uuid.uuid4()),
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("Ingestion job start failed: %s", exc.__class__.__name__)
            raise RuntimeError(
                "Failed to start Knowledge Base sync. Verify BEDROCK_DATA_SOURCE_ID "
                "points to the ScoutMatch S3 prefix."
            ) from exc

        job = response.get("ingestionJob") or {}
        job_id = job.get("ingestionJobId") or job.get("ingestion_job_id")
        status = job.get("status") or "STARTING"

        record = {
            "ingestion_job_id": job_id,
            "status": status,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "knowledge_base_id": kb_id,
            "data_source_id": ds_id,
        }
        with self._lock:
            self._latest_ingestion_job = record
        return record

    def get_ingestion_status(self, job_id: str | None = None) -> dict | None:
        """Poll ingestion job status via get_ingestion_job."""
        with self._lock:
            resolved_id = job_id or (
                self._latest_ingestion_job or {}
            ).get("ingestion_job_id")

        if not resolved_id:
            return None

        missing = config.validate_aws_config()
        if missing:
            return {
                "ingestion_job_id": resolved_id,
                "status": "UNKNOWN",
                "error": "Missing AWS configuration",
            }

        self._ensure_clients()
        kb_id = config.BEDROCK_KB_ID.strip()
        ds_id = config.BEDROCK_DATA_SOURCE_ID.strip()

        try:
            response = self._bedrock_agent.get_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=ds_id,
                ingestionJobId=resolved_id,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.error("get_ingestion_job failed: %s", exc.__class__.__name__)
            return {
                "ingestion_job_id": resolved_id,
                "status": "FAILED",
                "error": "Could not retrieve ingestion job status from AWS.",
            }

        job = response.get("ingestionJob") or {}
        status = job.get("status") or "UNKNOWN"
        record = {
            "ingestion_job_id": resolved_id,
            "status": status,
            "statistics": job.get("statistics") or {},
            "failure_reasons": job.get("failureReasons") or [],
        }
        with self._lock:
            if self._latest_ingestion_job and self._latest_ingestion_job.get(
                "ingestion_job_id"
            ) == resolved_id:
                self._latest_ingestion_job.update(record)
        return record

    def latest_ingestion_snapshot(self) -> dict | None:
        with self._lock:
            return dict(self._latest_ingestion_job) if self._latest_ingestion_job else None

    def list_documents(self) -> list[dict]:
        """List S3 objects under the ScoutMatch prefix only."""
        missing = config.validate_aws_config()
        if missing:
            return []

        self._ensure_clients()
        bucket = config.AWS_S3_BUCKET.strip()
        prefix = config.normalised_s3_prefix()
        docs: list[dict] = []

        paginator = self._s3.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents") or []:
                    key = obj.get("Key") or ""
                    if not key or key.endswith("/"):
                        continue
                    name = Path(key).name
                    ext = Path(key).suffix.lower().lstrip(".")
                    docs.append({
                        "key": key,
                        "name": key,
                        "display_name": name,
                        "display_source": name,
                        "size": obj.get("Size", 0),
                        "extension": ext,
                        "last_modified": (
                            obj.get("LastModified").isoformat()
                            if obj.get("LastModified")
                            else None
                        ),
                        "category": self._category_label(key, ext),
                        "s3_uri": f"s3://{bucket}/{key}",
                    })
        except (ClientError, BotoCoreError) as exc:
            logger.error("S3 list_objects failed: %s", exc.__class__.__name__)
            raise RuntimeError(
                "Failed to list documents from Amazon S3."
            ) from exc

        docs.sort(key=lambda d: d.get("display_name", "").lower())
        return docs

    @staticmethod
    def _category_label(key: str, ext: str) -> str:
        lower = key.lower()
        if "team_requirements" in lower:
            return "TEAM REQUIREMENTS"
        if "scouting_reports" in lower:
            return "SCOUT REPORT"
        if "player_cvs" in lower:
            return "PLAYER CV"
        ext_map = {
            "pdf": "PDF",
            "txt": "TXT",
            "md": "TXT",
            "doc": "DOCX",
            "docx": "DOCX",
            "csv": "CSV",
            "xls": "CSV",
            "xlsx": "CSV",
            "html": "TXT",
        }
        return ext_map.get(ext, ext.upper() if ext else "DOC")


# Module-level singleton used by Flask routes.
aws_storage = AWSStorageService()
