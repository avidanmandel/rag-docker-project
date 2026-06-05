"""
ScoutMatch football operations — dynamic squad planning, selections, and lineup boards.
"""

from __future__ import annotations

import os
import sys

_LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
_COMMON = os.path.join(_LAMBDA_ROOT, os.pardir, "common")
if _COMMON not in sys.path:
    sys.path.insert(0, os.path.normpath(_COMMON))
if _LAMBDA_ROOT not in sys.path:
    sys.path.insert(0, _LAMBDA_ROOT)

from availability import record_availability_change  # noqa: E402
from bedrock_response import (  # noqa: E402
    build_function_response,
    handle_action_errors,
    optional_string,
    require_string,
)
from lineup_svg import generate_board  # noqa: E402
from lineup_store import finalize_lineup  # noqa: E402
from player_selection import submit_selection  # noqa: E402
from squad_context import update_context  # noqa: E402
from squad_depth import analyze_depth_gaps  # noqa: E402
from write_confirmation import (  # noqa: E402
    is_write_confirmed,
    pending_confirmation_response,
)

ACTION_GROUP = "ScoutMatchFootballOperationsActionsAvidan"


def _update_context(params: dict, event: dict) -> dict:
    record, err = update_context(
        {
            "opponent": optional_string(params, "opponent"),
            "preferred_formation": params.get("preferred_formation") or params.get("formation"),
            "priority_positions": optional_string(params, "priority_positions"),
            "strong_positions": optional_string(params, "strong_positions"),
            "available_budget_eur": params.get("available_budget_eur"),
            "immediate_starter_required": params.get("immediate_starter_required"),
            "coach_notes": optional_string(params, "coach_notes"),
        }
    )
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="UpdateSquadPlanningContext",
            body={"status": "NEEDS_CLARIFICATION", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="UpdateSquadPlanningContext",
        body={"status": "SAVED", "context": record},
        event=event,
    )


def _submit_selection(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name="SubmitPlayerSelectionToManagement",
            message="Please confirm before reserving budget and notifying management.",
            event=event,
        )
    body, err = submit_selection(
        require_string(params, "candidate_name"),
        optional_string(params, "selection_reason") or "",
    )
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="SubmitPlayerSelectionToManagement",
            body={"status": "FAILURE", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="SubmitPlayerSelectionToManagement",
        body=body or {"status": "FAILURE"},
        event=event,
    )


def _finalize_lineup(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name="FinalizeCurrentLineup",
            message="Please confirm before saving the current starting lineup.",
            event=event,
        )
    record, err = finalize_lineup(params)
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="FinalizeCurrentLineup",
            body={"status": "REJECTED", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="FinalizeCurrentLineup",
        body={"status": "SAVED", "lineup": record},
        event=event,
    )


def _generate_board(params: dict, event: dict) -> dict:  # noqa: ARG001
    body, err = generate_board()
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="GenerateCurrentLineupBoard",
            body={"status": "NOT_FOUND", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="GenerateCurrentLineupBoard",
        body=body or {"status": "FAILURE"},
        event=event,
    )


def _record_availability(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name="RecordPlayerAvailabilityChange",
            message="Please confirm before recording an availability change.",
            event=event,
        )
    record, err = record_availability_change(
        require_string(params, "player_name"),
        require_string(params, "availability_status"),
        optional_string(params, "reason") or "",
    )
    if err:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="RecordPlayerAvailabilityChange",
            body={"status": "REJECTED", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="RecordPlayerAvailabilityChange",
        body={"status": "SAVED", "availability": record},
        event=event,
    )


def _analyze_depth(params: dict, event: dict) -> dict:  # noqa: ARG001
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="AnalyzeSquadDepthGaps",
        body={"status": "OK", "analysis": analyze_depth_gaps()},
        event=event,
    )


_HANDLERS = {
    "UpdateSquadPlanningContext": _update_context,
    "SubmitPlayerSelectionToManagement": _submit_selection,
    "FinalizeCurrentLineup": _finalize_lineup,
    "GenerateCurrentLineupBoard": _generate_board,
    "RecordPlayerAvailabilityChange": _record_availability,
    "AnalyzeSquadDepthGaps": _analyze_depth,
}


def lambda_handler(event, context):  # noqa: ARG001
    function_name = (event.get("function") or "").strip()
    handler = _HANDLERS.get(function_name)
    if not handler:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=function_name or "Unknown",
            body={"status": "FAILURE", "message": "Unknown football operations function."},
            event=event,
        )
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=function_name,
        event=event,
        handler=handler,
    )
