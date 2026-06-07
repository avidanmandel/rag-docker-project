"""OpenTransferOutReviewCase — legacy PlanMatchTactics when v2 disabled."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (_ROOT,):
    if path not in sys.path:
        sys.path.insert(0, path)

from bedrock_response import (  # noqa: E402
    build_function_response,
    handle_action_errors,
    optional_int,
    optional_string,
    require_string,
)
from feature_flags import business_workflow_v2_enabled  # noqa: E402
from write_confirmation import is_write_confirmed, is_write_denied, pending_confirmation_response  # noqa: E402

V2_ACTION_GROUP = "ScoutMatchTransferOutActionsAvidan"
V2_FUNCTION = "OpenTransferOutReviewCase"
LEGACY_ACTION_GROUP = "ScoutMatchTacticsActionsAvidan"
LEGACY_FUNCTION = "PlanMatchTactics"


def _config():
    if business_workflow_v2_enabled():
        return V2_ACTION_GROUP, V2_FUNCTION
    return LEGACY_ACTION_GROUP, LEGACY_FUNCTION


def _handle_v2(params: dict, event: dict, action_group: str, function_name: str) -> dict:
    from transfer_out_review import (  # noqa: E402
        deny_transfer_out_case,
        explain_transfer_out_candidate,
        open_transfer_out_case,
        prepare_transfer_out_case,
    )

    player_name = optional_string(params, "player_name") or optional_string(params, "candidate_name") or ""
    advisory_only = str(params.get("advisory_only") or "").lower() in {"1", "true", "yes"}
    if advisory_only or not player_name:
        body = explain_transfer_out_candidate(player_name or "Daniel Cohen")
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body=body,
            event=event,
        )
    if is_write_denied(event):
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body=deny_transfer_out_case(),
            event=event,
        )
    if not is_write_confirmed(event):
        body = prepare_transfer_out_case(
            player_name,
            review_reason=optional_string(params, "review_reason") or "",
        )
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body=body,
            event=event,
        )
    body, err = open_transfer_out_case(
        player_name,
        review_reason=optional_string(params, "review_reason") or "",
    )
    if err:
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body={"status": "FAILURE", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=action_group,
        function_name=function_name,
        body=body or {"status": "FAILURE"},
        event=event,
    )


def _handle_legacy(params: dict, event: dict, action_group: str, function_name: str) -> dict:
    from tactical_planner import plan_match_tactics  # noqa: E402

    squad_context = require_string(params, "squad_context")
    opponent = optional_string(params, "opponent") or ""
    body = plan_match_tactics(
        opponent=opponent,
        squad_context=squad_context,
        available_budget_eur=optional_int(params, "available_budget_eur"),
        preferred_style=optional_string(params, "preferred_style") or "",
        formation_options=optional_string(params, "formation_options") or "",
    )
    return build_function_response(
        action_group=action_group,
        function_name=function_name,
        body=body,
        event=event,
    )


def _handle(params: dict, event: dict) -> dict:
    action_group, function_name = _config()
    if business_workflow_v2_enabled():
        return _handle_v2(params, event, action_group, function_name)
    return _handle_legacy(params, event, action_group, function_name)


def lambda_handler(event, context):  # noqa: ARG001
    action_group, function_name = _config()
    return handle_action_errors(
        action_group=action_group,
        function_name=function_name,
        event=event,
        handler=_handle,
    )
