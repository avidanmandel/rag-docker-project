"""
Safe Flask helpers for private lineup SVG objects (Recruitment Advisor only).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import boto3

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env.agent", override=False)
except Exception:
    pass

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
LINEUP_BUCKET = os.getenv("SCOUTMATCH_LINEUP_BUCKET", os.getenv("AWS_S3_BUCKET", ""))
LINEUP_PREFIX = os.getenv(
    "SCOUTMATCH_LINEUP_S3_PREFIX", "scoutmatch/football-operations/lineups/"
)
FOOTBALL_OPS_TABLE = os.getenv(
    "SCOUTMATCH_FOOTBALL_OPS_TABLE", "ScoutMatchRecruitmentShortlistAvidan"
)
FOOTBALL_OPS_HASH_KEY = os.getenv("SCOUTMATCH_FOOTBALL_OPS_HASH_KEY", "candidate_key")
FOOTBALL_OPS_KEY_PREFIX = os.getenv("SCOUTMATCH_FOOTBALL_OPS_KEY_PREFIX", "football_ops#")
_LOCAL_SVG: dict[str, str] = {}
_LINEUP_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_valid_lineup_id(lineup_id: str) -> bool:
    return bool(_LINEUP_ID_PATTERN.match(lineup_id or ""))


def register_local_svg(lineup_id: str, svg: str) -> None:
    _LOCAL_SVG[lineup_id] = svg


def _storage_key(entity_key: str) -> str:
    return f"{FOOTBALL_OPS_KEY_PREFIX}{entity_key}" if FOOTBALL_OPS_KEY_PREFIX else entity_key


def _object_key_from_metadata(lineup_id: str) -> str:
    """Read latest SVG object key from DynamoDB board metadata (GetObject-only path)."""
    entity_key = f"lineup_board#{lineup_id}"
    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(FOOTBALL_OPS_TABLE)
    resp = table.get_item(Key={FOOTBALL_OPS_HASH_KEY: _storage_key(entity_key)})
    item = resp.get("Item") or {}
    payload = json.loads(item.get("operations_json") or "{}")
    return str(payload.get("object_key") or "").strip()


def _read_svg_object(client, object_key: str) -> tuple[str | None, str]:
    if not object_key:
        return None, "Lineup image not found."
    body = client.get_object(Bucket=LINEUP_BUCKET, Key=object_key)["Body"].read()
    return body.decode("utf-8", errors="replace"), ""


def fetch_lineup_svg(lineup_id: str) -> tuple[str | None, str]:
    if not is_valid_lineup_id(lineup_id):
        return None, "Invalid lineup identifier."
    if lineup_id in _LOCAL_SVG:
        return _LOCAL_SVG[lineup_id], ""
    if not LINEUP_BUCKET.strip():
        return None, "Lineup image storage is not configured."
    client = boto3.client("s3", region_name=AWS_REGION)
    try:
        object_key = _object_key_from_metadata(lineup_id)
        if object_key:
            return _read_svg_object(client, object_key)
    except Exception:
        pass
    prefix = f"{LINEUP_PREFIX.rstrip('/')}/{lineup_id}/"
    try:
        listed = client.list_objects_v2(Bucket=LINEUP_BUCKET, Prefix=prefix, MaxKeys=20)
        keys = [
            obj["Key"]
            for obj in listed.get("Contents", [])
            if str(obj.get("Key", "")).endswith(".svg")
        ]
        if not keys:
            return None, "Lineup image not found."
        latest_key = sorted(keys)[-1]
        return _read_svg_object(client, latest_key)
    except Exception:
        return None, "Lineup image is not accessible from the application host."
