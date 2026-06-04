"""
ScoutMatchShortlistManagerAvidan — recruitment shortlist (DynamoDB or local memory).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

_LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
_COMMON = os.path.join(_LAMBDA_ROOT, os.pardir, "common")
if _COMMON not in sys.path:
    sys.path.insert(0, os.path.normpath(_COMMON))

from bedrock_response import (  # noqa: E402
    build_function_response,
    handle_action_errors,
    optional_string,
    require_string,
)
from write_confirmation import (  # noqa: E402
    WRITE_ACTIONS,
    is_write_confirmed,
    pending_confirmation_response,
)

ACTION_GROUP = "ScoutMatchShortlistActionsAvidan"
TABLE_NAME = os.getenv("SCOUTMATCH_SHORTLIST_TABLE", "ScoutMatchRecruitmentShortlistAvidan")
_LOCAL_STORE: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _key(candidate_name: str) -> str:
    return candidate_name.strip().lower()


def _ddb_table():
    import boto3

    return boto3.resource("dynamodb").Table(TABLE_NAME)


def _use_ddb() -> bool:
    return os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() not in {"1", "true", "yes"}


def _get_item(candidate_name: str) -> dict | None:
    key = _key(candidate_name)
    if not _use_ddb():
        return _LOCAL_STORE.get(key)
    resp = _ddb_table().get_item(Key={"candidate_key": key})
    return resp.get("Item")


def _put_item(item: dict) -> None:
    key = item["candidate_key"]
    if not _use_ddb():
        _LOCAL_STORE[key] = item
        return
    _ddb_table().put_item(Item=item)


def _delete_item(candidate_name: str) -> bool:
    key = _key(candidate_name)
    if not _use_ddb():
        return _LOCAL_STORE.pop(key, None) is not None
    resp = _ddb_table().delete_item(Key={"candidate_key": key}, ReturnValues="ALL_OLD")
    return bool(resp.get("Attributes"))


def _list_items(target_role: str | None, status: str | None) -> list[dict]:
    if not _use_ddb():
        items = list(_LOCAL_STORE.values())
    else:
        items = []
        table = _ddb_table()
        scan_kwargs: dict = {}
        while True:
            page = table.scan(**scan_kwargs)
            items.extend(page.get("Items", []))
            token = page.get("LastEvaluatedKey")
            if not token:
                break
            scan_kwargs["ExclusiveStartKey"] = token
    results = []
    for item in items:
        if target_role and item.get("target_role") != target_role:
            continue
        if status and item.get("status") != status:
            continue
        results.append(_sanitize_entry(item))
    return sorted(results, key=lambda x: x["candidate_name"])


def _sanitize_entry(item: dict) -> dict:
    return {
        "candidate_name": item.get("candidate_name", ""),
        "target_role": item.get("target_role", ""),
        "status": item.get("status", ""),
        "recruitment_note": item.get("recruitment_note") or "",
        "source_context": item.get("source_context") or "",
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    }


def _guard_write(function_name: str, event: dict) -> dict | None:
    from write_confirmation import is_write_denied  # noqa: E402

    if is_write_denied(event):
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=function_name,
            body={"status": "DENIED", "message": "Write cancelled by coach."},
            event=event,
        )
    if function_name in WRITE_ACTIONS and not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name=function_name,
            message=(
                "Please confirm this shortlist change before it is saved. "
                "Set session write_confirmed=true after the coach approves."
            ),
            event=event,
        )
    return None


def _add(params: dict, event: dict) -> dict:
    pending = _guard_write("AddCandidateToShortlist", event)
    if pending:
        return pending
    candidate_name = require_string(params, "candidate_name")
    target_role = require_string(params, "target_role")
    status = require_string(params, "status")
    note = optional_string(params, "recruitment_note")
    source = optional_string(params, "source_context")
    now = _now()
    item = {
        "candidate_key": _key(candidate_name),
        "candidate_name": candidate_name,
        "target_role": target_role,
        "status": status,
        "recruitment_note": note or "",
        "source_context": source or "",
        "created_at": now,
        "updated_at": now,
    }
    _put_item(item)
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="AddCandidateToShortlist",
        body={"status": "SAVED", "candidate": _sanitize_entry(item)},
        event=event,
    )


def _list(params: dict, event: dict) -> dict:
    target_role = optional_string(params, "target_role")
    status = optional_string(params, "status")
    entries = _list_items(target_role, status)
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="ListShortlistCandidates",
        body={"candidates": entries, "count": len(entries)},
        event=event,
    )


def _update(params: dict, event: dict) -> dict:
    pending = _guard_write("UpdateCandidateShortlistStatus", event)
    if pending:
        return pending
    candidate_name = require_string(params, "candidate_name")
    status = require_string(params, "status")
    note = optional_string(params, "recruitment_note")
    item = _get_item(candidate_name)
    if not item:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="UpdateCandidateShortlistStatus",
            body={"status": "NOT_FOUND", "candidate_name": candidate_name},
            event=event,
        )
    item["status"] = status
    if note is not None:
        item["recruitment_note"] = note
    item["updated_at"] = _now()
    _put_item(item)
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="UpdateCandidateShortlistStatus",
        body={"status": "UPDATED", "candidate": _sanitize_entry(item)},
        event=event,
    )


def _remove(params: dict, event: dict) -> dict:
    pending = _guard_write("RemoveCandidateFromShortlist", event)
    if pending:
        return pending
    candidate_name = require_string(params, "candidate_name")
    removed = _delete_item(candidate_name)
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="RemoveCandidateFromShortlist",
        body={
            "status": "REMOVED" if removed else "NOT_FOUND",
            "candidate_name": candidate_name,
        },
        event=event,
    )


_HANDLERS = {
    "AddCandidateToShortlist": _add,
    "ListShortlistCandidates": _list,
    "UpdateCandidateShortlistStatus": _update,
    "RemoveCandidateFromShortlist": _remove,
}


def lambda_handler(event, context):  # noqa: ARG001
    function_name = (event.get("function") or "").strip()
    handler = _HANDLERS.get(function_name)
    if not handler:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=function_name or "Unknown",
            body={"status": "FAILURE", "message": "Unknown shortlist function."},
            event=event,
        )

    def _run(params, evt):
        return handler(params, evt)

    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=function_name,
        event=event,
        handler=_run,
    )
