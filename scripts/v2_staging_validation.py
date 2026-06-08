"""Alias-aware Business Workflow V2 staging validation helpers."""

from __future__ import annotations

import json
import re
from typing import Any

V2_LAMBDA_ALIAS = "scoutmatch-v2-staging"
PRODUCTION_AGENT_ALIAS = "MFWBSFNIDL"
PRODUCTION_AGENT_VERSION = "22"
STAGING_AGENT_ALIAS = "T6N3TXAMCJ"

V2_PROBE_MAP = {
    "SubmitCriticalDecisionAndSendEmail": "ScoutMatchSubmitPlayerSelectionAvidan",
    "OpenTransferOutReviewCase": "ScoutMatchPlanMatchTacticsAvidan",
    "CreateAndReviewScoutingMission": "ScoutMatchFinalizeCurrentLineupAvidan",
    "GenerateVisualSquadAndLineupBoard": "ScoutMatchGenerateLineupBoardAvidan",
}

V2_ACTION_GROUPS = {
    "ScoutMatchCritDecisionAvidan",
    "ScoutMatchTransferOutAvidan",
    "ScoutMatchScoutMissionAvidan",
    "ScoutMatchSquadBoardAvidan",
}

ACCOUNT_ID_PATTERN = re.compile(r"\b\d{12}\b")
ARN_PATTERN = re.compile(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:")


def v2_probe_target(function_name: str) -> str:
    if function_name not in V2_PROBE_MAP:
        raise KeyError(f"Unknown V2 probe function: {function_name}")
    return f"{V2_PROBE_MAP[function_name]}:{V2_LAMBDA_ALIAS}"


def assert_v2_probe_target(target: str) -> None:
    if target.endswith(":LATEST") or target == "LATEST":
        raise ValueError(f"V2 probe must not target $LATEST: {target!r}")
    if ":" not in target:
        raise ValueError(
            f"V2 probe must use published alias {V2_LAMBDA_ALIAS!r}, not unqualified name: {target!r}"
        )
    alias = target.rsplit(":", 1)[-1]
    if alias != V2_LAMBDA_ALIAS:
        raise ValueError(f"V2 probe must use alias {V2_LAMBDA_ALIAS!r}, got {alias!r}")


def sanitize_public_report(report: dict[str, Any]) -> dict[str, Any]:
    """Drop account IDs and raw ARNs from validation output."""

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v) for v in value]
        if isinstance(value, str):
            if ARN_PATTERN.search(value):
                return "<redacted-arn>"
            return ACCOUNT_ID_PATTERN.sub("<redacted-account>", value)
        return value

    return _walk(report)


def parse_lambda_body(raw: dict) -> dict:
    try:
        text = (
            raw.get("response", {})
            .get("functionResponse", {})
            .get("responseBody", {})
            .get("TEXT", {})
            .get("body", "{}")
        )
        return json.loads(text) if isinstance(text, str) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def invoke_lambda(client, target: str, event: dict, *, v2_probe: bool = False) -> dict:
    if v2_probe:
        assert_v2_probe_target(target)
    resp = client.invoke(
        FunctionName=target,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode("utf-8"),
    )
    raw = json.loads(resp["Payload"].read())
    if "FunctionError" in resp:
        return {"status": "FUNCTION_ERROR", "raw": raw}
    return parse_lambda_body(raw)
