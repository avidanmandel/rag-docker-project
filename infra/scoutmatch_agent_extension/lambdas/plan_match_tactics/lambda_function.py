"""ScoutMatchPlanMatchTacticsAvidan — PlanMatchTactics."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (_ROOT,):
    if path not in sys.path:
        sys.path.insert(0, path)

from bedrock_response import build_function_response, handle_action_errors, optional_int, optional_string, require_string  # noqa: E402
from tactical_planner import plan_match_tactics  # noqa: E402

ACTION_GROUP = "ScoutMatchTacticsActionsAvidan"
FUNCTION_NAME = "PlanMatchTactics"


def _handle(params: dict, event: dict) -> dict:
    body = plan_match_tactics(
        opponent=require_string(params, "opponent"),
        squad_context=require_string(params, "squad_context"),
        available_budget_eur=optional_int(params, "available_budget_eur"),
        preferred_style=optional_string(params, "preferred_style") or "",
        formation_options=optional_string(params, "formation_options") or "",
    )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        body=body,
        event=event,
    )


def lambda_handler(event, context):  # noqa: ARG001
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        event=event,
        handler=_handle,
    )
