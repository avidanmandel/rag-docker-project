"""ScoutMatchGenerateLineupBoardAvidan — GenerateCurrentLineupBoard."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (_ROOT,):
    if path not in sys.path:
        sys.path.insert(0, path)

from bedrock_response import build_function_response, handle_action_errors, optional_string  # noqa: E402
from lineup_svg import generate_board  # noqa: E402

ACTION_GROUP = "ScoutMatchLineupBoardActionsAvidan"
FUNCTION_NAME = "GenerateCurrentLineupBoard"


def _handle(params: dict, event: dict) -> dict:
    body, err = generate_board(optional_string(params, "lineup_id") or "")
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=FUNCTION_NAME,
            body={"status": "NOT_FOUND", "message": err},
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
