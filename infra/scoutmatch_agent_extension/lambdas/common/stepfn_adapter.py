"""
Transform simple workflow payloads into Bedrock Action Group Lambda events.

Preserves existing Action Group contracts for direct Bedrock invocation.
Step Functions and the workflow orchestrator use this adapter only.
"""

from __future__ import annotations

import json
from typing import Any


def bedrock_action_event(
    *,
    action_group: str,
    function_name: str,
    parameters: dict[str, Any],
    session_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "actionGroup": action_group,
        "function": function_name,
        "parameters": [
            {"name": key, "value": str(value)}
            for key, value in parameters.items()
            if value is not None
        ],
    }
    if session_attributes:
        event["sessionAttributes"] = session_attributes
    return event


def parse_function_body(lambda_result: dict[str, Any]) -> dict[str, Any]:
    """Extract JSON body from a Bedrock-shaped Lambda response."""
    try:
        text = (
            lambda_result.get("response", {})
            .get("functionResponse", {})
            .get("responseBody", {})
            .get("TEXT", {})
            .get("body", "{}")
        )
        return json.loads(text) if isinstance(text, str) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def sanitize_workflow_reference(execution_name: str) -> str:
    """Return a short opaque reference — never a full execution ARN."""
    token = execution_name.split(":")[-1] if ":" in execution_name else execution_name
    return f"review-{token[-12:].lower()}"
