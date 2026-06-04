"""
ScoutMatchRecruitmentBriefAvidan — sanitized recruitment briefs in S3 (or local memory).
"""

from __future__ import annotations

import json
import os
import re
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
    is_write_confirmed,
    pending_confirmation_response,
)

ACTION_GROUP = "ScoutMatchRecruitmentBriefActionsAvidan"
BUCKET = os.getenv("SCOUTMATCH_BRIEF_BUCKET", "")
PREFIX = os.getenv("SCOUTMATCH_BRIEF_PREFIX", "scoutmatch/recruitment-advisor/briefs/")
_LOCAL_STORE: dict[str, list[dict]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return token or "candidate"


def _object_key(candidate_name: str, created_at: str) -> str:
    stamp = created_at.replace(":", "").replace("+00:00", "Z")
    return f"{PREFIX.rstrip('/')}/{_slug(candidate_name)}/{stamp}.json"


def _use_local() -> bool:
    return (
        os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}
        or not BUCKET.strip()
    )


def _save_brief(record: dict) -> str:
    key = _object_key(record["candidate_name"], record["created_at"])
    if _use_local():
        bucket = _LOCAL_STORE.setdefault(record["candidate_name"], [])
        bucket.append({**record, "object_key": key})
        return key
    import boto3

    boto3.client("s3").put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(record, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    return key


def _load_briefs(candidate_name: str | None = None) -> list[dict]:
    if _use_local():
        if candidate_name:
            return list(_LOCAL_STORE.get(candidate_name, []))
        all_items: list[dict] = []
        for items in _LOCAL_STORE.values():
            all_items.extend(items)
        return all_items
    import boto3

    client = boto3.client("s3")
    prefix = PREFIX.rstrip("/") + "/"
    if candidate_name:
        prefix += f"{_slug(candidate_name)}/"
    keys: list[str] = []
    token = None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                keys.append(obj["Key"])
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    records = []
    for key in keys:
        body = client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        records.append(json.loads(body))
    return records


def _build_brief(params: dict) -> dict:
    created_at = _now()
    candidate_name = require_string(params, "candidate_name")
    return {
        "candidate_name": candidate_name,
        "target_role": require_string(params, "target_role"),
        "tactical_decision": require_string(params, "tactical_decision"),
        "budget_decision": require_string(params, "budget_decision"),
        "missing_information": optional_string(params, "missing_information") or "",
        "created_at": created_at,
        "markdown_summary": (
            f"# Recruitment brief — {candidate_name}\n\n"
            f"- Target role: {params['target_role']}\n"
            f"- Tactical decision: {params['tactical_decision']}\n"
            f"- Budget decision: {params['budget_decision']}\n"
            f"- Missing information: {optional_string(params, 'missing_information') or 'None noted'}\n"
            f"- Created at: {created_at}\n"
        ),
    }


def _summarize(record: dict) -> dict:
    return {
        "candidate_name": record["candidate_name"],
        "target_role": record["target_role"],
        "tactical_decision": record["tactical_decision"],
        "budget_decision": record["budget_decision"],
        "missing_information": record.get("missing_information", ""),
        "created_at": record["created_at"],
        "object_key": record.get("object_key") or _object_key(
            record["candidate_name"], record["created_at"]
        ),
    }


def _create(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name="CreateRecruitmentBrief",
            message="Please confirm before creating a recruitment brief for staff review.",
            event=event,
        )
    record = _build_brief(params)
    key = _save_brief(record)
    record["object_key"] = key
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="CreateRecruitmentBrief",
        body={"status": "CREATED", "brief": _summarize(record)},
        event=event,
    )


def _get(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    records = _load_briefs(candidate_name)
    if not records:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="GetRecruitmentBrief",
            body={"status": "NOT_FOUND", "candidate_name": candidate_name},
            event=event,
        )
    latest = sorted(records, key=lambda r: r["created_at"])[-1]
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="GetRecruitmentBrief",
        body={"status": "FOUND", "brief": _summarize(latest)},
        event=event,
    )


def _list(params: dict, event: dict) -> dict:
    target_role = optional_string(params, "target_role")
    records = _load_briefs()
    summaries = []
    for record in sorted(records, key=lambda r: r["created_at"], reverse=True):
        if target_role and record.get("target_role") != target_role:
            continue
        summaries.append(_summarize(record))
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="ListRecruitmentBriefs",
        body={"briefs": summaries, "count": len(summaries)},
        event=event,
    )


_HANDLERS = {
    "CreateRecruitmentBrief": _create,
    "GetRecruitmentBrief": _get,
    "ListRecruitmentBriefs": _list,
}


def lambda_handler(event, context):  # noqa: ARG001
    function_name = (event.get("function") or "").strip()
    handler = _HANDLERS.get(function_name)
    if not handler:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=function_name or "Unknown",
            body={"status": "FAILURE", "message": "Unknown recruitment brief function."},
            event=event,
        )

    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=function_name,
        event=event,
        handler=handler,
    )
