"""DynamoDB / local store for ScoutMatchFootballOperationsAvidan."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

TABLE_NAME = os.getenv(
    "SCOUTMATCH_FOOTBALL_OPS_TABLE", "ScoutMatchFootballOperationsAvidan"
)
_LOCAL_STORE: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _use_ddb() -> bool:
    return os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() not in {"1", "true", "yes"}


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(TABLE_NAME)


def get_item(entity_key: str) -> dict | None:
    if not _use_ddb():
        return _LOCAL_STORE.get(entity_key)
    resp = _table().get_item(Key={"entity_key": entity_key})
    item = resp.get("Item")
    if not item:
        return None
    payload = json.loads(item.get("operations_json") or "{}")
    payload["entity_key"] = entity_key
    payload["item_type"] = item.get("item_type", "")
    payload["updated_at"] = item.get("updated_at", "")
    return payload


def put_item(*, entity_key: str, item_type: str, payload: dict) -> dict:
    record = {**payload, "entity_key": entity_key, "item_type": item_type, "updated_at": _now()}
    if not _use_ddb():
        _LOCAL_STORE[entity_key] = record
        return record
    _table().put_item(
        Item={
            "entity_key": entity_key,
            "item_type": item_type,
            "operations_json": json.dumps(
                {k: v for k, v in record.items() if k not in {"entity_key", "item_type"}}
            ),
            "updated_at": record["updated_at"],
        }
    )
    return record


def list_by_prefix(prefix: str) -> list[dict]:
    if not _use_ddb():
        return [v for k, v in _LOCAL_STORE.items() if k.startswith(prefix)]
    items: list[dict] = []
    table = _table()
    token = None
    while True:
        kwargs = {"FilterExpression": "begins_with(entity_key, :p)", "ExpressionAttributeValues": {":p": prefix}}
        if token:
            kwargs["ExclusiveStartKey"] = token
        page = table.scan(**kwargs)
        for row in page.get("Items", []):
            payload = json.loads(row.get("operations_json") or "{}")
            payload["entity_key"] = row["entity_key"]
            payload["item_type"] = row.get("item_type", "")
            items.append(payload)
        token = page.get("LastEvaluatedKey")
        if not token:
            break
    return items


def clear_local_store() -> None:
    _LOCAL_STORE.clear()
