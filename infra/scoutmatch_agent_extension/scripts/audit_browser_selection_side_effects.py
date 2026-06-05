#!/usr/bin/env python3
"""Read-only audit for browser player-selection side effects."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[3]
REGION = "us-east-1"
TABLE = os.getenv("SCOUTMATCH_FOOTBALL_OPS_TABLE", "ScoutMatchRecruitmentShortlistAvidan")
PREFIX = os.getenv("SCOUTMATCH_FOOTBALL_OPS_KEY_PREFIX", "football_ops#")
HASH_KEY = os.getenv("SCOUTMATCH_FOOTBALL_OPS_HASH_KEY", "candidate_key")


def _redact_key(key: str) -> str:
    return re.sub(r"ron\s*ben\s*ari", "ron-[redacted]", key, flags=re.I)


def main() -> int:
    ddb = boto3.client("dynamodb", region_name=REGION)
    selection_keys: list[str] = []
    ledger_keys: list[str] = []
    try:
        token = None
        while True:
            kwargs = {"TableName": TABLE}
            if token:
                kwargs["ExclusiveStartKey"] = token
            page = ddb.scan(**kwargs)
            for item in page.get("Items", []):
                raw = item.get(HASH_KEY, {}).get("S") or item.get("entity_key", {}).get("S", "")
                if not raw.startswith(PREFIX):
                    continue
                logical = raw[len(PREFIX) :] if raw.startswith(PREFIX) else raw
                item_type = item.get("item_type", {}).get("S", "")
                if logical.startswith("player_selection#") or item_type == "PLAYER_SELECTION":
                    selection_keys.append(_redact_key(logical))
                if logical.startswith("budget_ledger#") or item_type == "BUDGET_LEDGER":
                    ledger_keys.append(_redact_key(logical))
            token = page.get("LastEvaluatedKey")
            if not token:
                break
    except ClientError as exc:
        print(
            json.dumps(
                {
                    "result": "AUDIT_INCOMPLETE",
                    "error_code": exc.response.get("Error", {}).get("Code"),
                },
                indent=2,
            )
        )
        return 2

    detected = bool(selection_keys or ledger_keys)
    print(
        json.dumps(
            {
                "result": "DEMO_SIDE_EFFECT_DETECTED" if detected else "NO_SIDE_EFFECTS_DETECTED",
                "player_selection_record_count": len(selection_keys),
                "budget_ledger_record_count": len(ledger_keys),
                "sanitized_selection_keys_sample": selection_keys[:5],
                "sanitized_ledger_keys_sample": ledger_keys[:5],
                "cleanup_plan": (
                    "Manual cleanup deferred. If approved, delete only football_ops# demo "
                    "PLAYER_SELECTION and BUDGET_LEDGER items for the browser test session."
                    if detected
                    else "No cleanup required."
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
