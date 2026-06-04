"""
Reusable helpers for Amazon Bedrock Agent Action Group Lambda responses.

Stdlib only. No secrets logging.
"""

from __future__ import annotations

import json
import re
from typing import Any


MESSAGE_VERSION = "1.0"


class ParameterError(ValueError):
    """Invalid or missing Action Group parameters."""


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", key.lower().replace("-", "_"))


def parse_function_parameters(event: dict[str, Any]) -> dict[str, Any]:
    """Extract parameters from a Bedrock Action Group invoke event."""
    params: dict[str, Any] = {}
    for block in event.get("parameters") or []:
        if isinstance(block, dict) and block.get("name") is not None:
            params[block["name"]] = block.get("value")
            continue
    for detail in event.get("functionDetails", {}).get("parameters") or []:
        if isinstance(detail, dict) and detail.get("name") is not None:
            params[detail["name"]] = detail.get("value")
    request_body = event.get("requestBody") or {}
    for _content_type, body in request_body.items():
        if not isinstance(body, dict):
            continue
        for prop in body.get("properties") or []:
            if isinstance(prop, dict) and prop.get("name") is not None:
                params[prop["name"]] = prop.get("value")
    return params


def require_string(params: dict[str, Any], name: str) -> str:
    if name not in params or params[name] is None:
        raise ParameterError(f"Missing required parameter: {name}")
    value = str(params[name]).strip()
    if not value:
        raise ParameterError(f"Missing required parameter: {name}")
    return value


def require_int(params: dict[str, Any], name: str) -> int:
    if name not in params or params[name] is None or str(params[name]).strip() == "":
        raise ParameterError(f"Missing required parameter: {name}")
    try:
        return int(str(params[name]).strip().replace(",", ""))
    except ValueError as exc:
        raise ParameterError(f"Invalid integer for {name}") from exc


def require_bool(params: dict[str, Any], name: str) -> bool:
    if name not in params or params[name] is None or str(params[name]).strip() == "":
        raise ParameterError(f"Missing required parameter: {name}")
    raw = str(params[name]).strip().lower()
    if raw in {"true", "1", "yes", "y"}:
        return True
    if raw in {"false", "0", "no", "n"}:
        return False
    raise ParameterError(f"Invalid boolean for {name}")


def optional_string(params: dict[str, Any], name: str) -> str | None:
    if name not in params or params[name] is None:
        return None
    value = str(params[name]).strip()
    return value or None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def qualitative_rating(value: str) -> str:
    """Return POSITIVE, NEGATIVE, NEUTRAL, or UNKNOWN for tactical text."""
    text = normalize_text(value)
    if not text or text in {"unknown", "n/a", "na", "not documented", "missing", "none"}:
        return "UNKNOWN"
    negative = (
        "poor",
        "weak",
        "low",
        "limited",
        "below",
        "insufficient",
        "no ",
        "not ",
        "unavailable",
        "delayed",
    )
    positive = (
        "excellent",
        "strong",
        "good",
        "high",
        "accurate",
        "effective",
        "preferred",
        "immediate",
        "yes",
        "capable",
        "solid",
    )
    if any(token in text for token in negative):
        return "NEGATIVE"
    if any(token in text for token in positive):
        return "POSITIVE"
    return "NEUTRAL"


def safe_json_body(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def build_function_response(
    *,
    action_group: str,
    function_name: str,
    body: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "messageVersion": MESSAGE_VERSION,
        "response": {
            "actionGroup": action_group,
            "function": function_name,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": safe_json_body(body),
                    }
                }
            },
        },
    }
    session_attrs = event.get("sessionAttributes")
    prompt_attrs = event.get("promptSessionAttributes")
    if isinstance(session_attrs, dict):
        response["sessionAttributes"] = session_attrs
    if isinstance(prompt_attrs, dict):
        response["promptSessionAttributes"] = prompt_attrs
    return response


def build_reprompt(
    *,
    action_group: str,
    function_name: str,
    message: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    response = build_function_response(
        action_group=action_group,
        function_name=function_name,
        body={"status": "REPROMPT", "message": message},
        event=event,
    )
    response["response"]["functionResponse"]["responseState"] = "REPROMPT"
    return response


def build_failure(
    *,
    action_group: str,
    function_name: str,
    message: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    response = build_function_response(
        action_group=action_group,
        function_name=function_name,
        body={"status": "FAILURE", "message": message},
        event=event,
    )
    response["response"]["functionResponse"]["responseState"] = "FAILURE"
    return response


def handle_action_errors(
    *,
    action_group: str,
    function_name: str,
    event: dict[str, Any],
    handler,
) -> dict[str, Any]:
    try:
        params = parse_function_parameters(event)
        return handler(params, event)
    except ParameterError as exc:
        return build_reprompt(
            action_group=action_group,
            function_name=function_name,
            message=str(exc),
            event=event,
        )
    except Exception:
        return build_failure(
            action_group=action_group,
            function_name=function_name,
            message="The recruitment tool could not complete this request.",
            event=event,
        )
