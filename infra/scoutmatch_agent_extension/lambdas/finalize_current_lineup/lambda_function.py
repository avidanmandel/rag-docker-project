"""ScoutMatchFinalizeCurrentLineupAvidan — FinalizeCurrentLineup."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (_ROOT,):
    if path not in sys.path:
        sys.path.insert(0, path)

from bedrock_response import build_function_response, handle_action_errors, optional_string  # noqa: E402
from lineup_store import finalize_lineup  # noqa: E402
from write_confirmation import is_write_confirmed, pending_confirmation_response  # noqa: E402

ACTION_GROUP = "ScoutMatchLineupActionsAvidan"
FUNCTION_NAME = "FinalizeCurrentLineup"


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "demo"}


def _handle(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name=FUNCTION_NAME,
            message="Please confirm before saving the current starting lineup.",
            event=event,
        )
    record, err = finalize_lineup(
        {
            "formation": optional_string(params, "formation") or "",
            "lineup_json": optional_string(params, "lineup_json") or optional_string(params, "starting_xi") or "",
            "demo_lineup": _truthy(params.get("demo_lineup")),
            "opponent": optional_string(params, "opponent") or "",
            "planning_context_id": optional_string(params, "planning_context_id") or "",
        }
    )
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=FUNCTION_NAME,
            body={"status": "REJECTED", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        body=record or {"status": "FAILURE"},
        event=event,
    )


def lambda_handler(event, context):  # noqa: ARG001
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        event=event,
        handler=_handle,
    )
