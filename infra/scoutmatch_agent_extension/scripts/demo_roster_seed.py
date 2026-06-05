"""Deploy-time idempotent demo roster seed (imported by deploy_scoutmatch_extension)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXT = Path(__file__).resolve().parents[1]
OPS = EXT / "lambdas" / "football_operations"
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))

from demo_roster import (  # noqa: E402
    DEMO_RECORD_SCOPE,
    DEMO_ROSTER_ENTITY_KEY,
    load_demo_roster_from_file,
)


def plan_demo_roster_seed() -> str:
    return (
        f"Seed sanitized demo roster into {os.getenv('SCOUTMATCH_FOOTBALL_OPS_TABLE', 'ScoutMatchFootballOperationsAvidan')} "
        f"at {DEMO_ROSTER_ENTITY_KEY} with record_scope={DEMO_RECORD_SCOPE} (skip non-demo records)"
    )


def apply_demo_roster_seed(*, table_name: str, apply: bool, ddb_client=None) -> dict:
    payload = load_demo_roster_from_file()
    if payload.get("record_scope") != DEMO_RECORD_SCOPE:
        return {"status": "REJECTED", "reason": "invalid_record_scope"}
    if len(payload.get("players") or []) != 11:
        return {"status": "REJECTED", "reason": "invalid_player_count"}

    if not apply:
        return {"status": "PLANNED", "entity_key": DEMO_ROSTER_ENTITY_KEY}

    if ddb_client is None:
        import boto3

        ddb_client = boto3.client("dynamodb")

    try:
        existing = ddb_client.get_item(TableName=table_name, Key={"entity_key": {"S": DEMO_ROSTER_ENTITY_KEY}})
        item = existing.get("Item")
        if item:
            body = json.loads(item.get("operations_json", {}).get("S", "{}"))
            scope = body.get("record_scope", "")
            if scope and scope != DEMO_RECORD_SCOPE:
                return {"status": "SKIPPED", "reason": "non_demo_record_present"}
            if scope == DEMO_RECORD_SCOPE:
                return {"status": "ALREADY_SEEDED"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "ERROR", "reason": str(exc)}

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    record = {**payload, "entity_key": DEMO_ROSTER_ENTITY_KEY, "record_scope": DEMO_RECORD_SCOPE}
    ddb_client.put_item(
        TableName=table_name,
        Item={
            "entity_key": {"S": DEMO_ROSTER_ENTITY_KEY},
            "item_type": {"S": "DEMO_ROSTER"},
            "operations_json": {"S": json.dumps({k: v for k, v in record.items() if k != "entity_key"})},
            "updated_at": {"S": now},
        },
    )
    return {"status": "SEEDED", "entity_key": DEMO_ROSTER_ENTITY_KEY}
