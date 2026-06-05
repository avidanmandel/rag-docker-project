"""ScoutMatchSubmitPlayerSelectionAvidan — SubmitPlayerSelectionToManagement."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (_ROOT,):
    if path not in sys.path:
        sys.path.insert(0, path)

from bedrock_response import build_function_response, handle_action_errors, optional_int, optional_string, require_string  # noqa: E402
from player_selection import submit_selection  # noqa: E402
from write_confirmation import is_write_confirmed, pending_confirmation_response  # noqa: E402

ACTION_GROUP = "ScoutMatchPlayerSelectionActionsAvidan"
FUNCTION_NAME = "SubmitPlayerSelectionToManagement"


def _handle(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name=FUNCTION_NAME,
            message="Please confirm before reserving budget and notifying management.",
            event=event,
        )
    body, err = submit_selection(
        require_string(params, "candidate_name"),
        target_role=optional_string(params, "target_role") or "",
        salary_eur=optional_int(params, "salary_eur"),
        selection_reason=optional_string(params, "selection_reason") or "",
    )
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=FUNCTION_NAME,
            body={"status": "FAILURE", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        body=body or {"status": "FAILURE"},
        event=event,
    )


def lambda_handler(event, context):  # noqa: ARG001
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        event=event,
        handler=_handle,
    )
