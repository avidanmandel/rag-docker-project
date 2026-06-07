"""CreateAndReviewScoutingMission — legacy FinalizeCurrentLineup when v2 disabled."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for path in (_ROOT,):
    if path not in sys.path:
        sys.path.insert(0, path)

from bedrock_response import build_function_response, handle_action_errors, optional_string  # noqa: E402
from feature_flags import business_workflow_v2_enabled  # noqa: E402
from write_confirmation import is_write_confirmed, is_write_denied, pending_confirmation_response  # noqa: E402

V2_ACTION_GROUP = "ScoutMatchScoutingMissionActionsAvidan"
V2_FUNCTION = "CreateAndReviewScoutingMission"
LEGACY_ACTION_GROUP = "ScoutMatchLineupActionsAvidan"
LEGACY_FUNCTION = "FinalizeCurrentLineup"


def _config():
    if business_workflow_v2_enabled():
        return V2_ACTION_GROUP, V2_FUNCTION
    return LEGACY_ACTION_GROUP, LEGACY_FUNCTION


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "demo"}


def _handle_v2(params: dict, event: dict, action_group: str, function_name: str) -> dict:
    from scouting_mission import (  # noqa: E402
        create_scouting_mission,
        deny_scouting_mission,
        prepare_scouting_mission,
        review_completed_mission,
    )

    mode = (optional_string(params, "mission_mode") or "CREATE_MISSION").upper()
    candidate_name = optional_string(params, "candidate_name") or ""
    if mode == "REVIEW_COMPLETED_MISSION":
        body = review_completed_mission(candidate_name or "Ron Ben Ari")
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
            body=deny_scouting_mission(),
            event=event,
        )
    if not is_write_confirmed(event):
        body = prepare_scouting_mission(
            candidate_name=candidate_name or "Ron Ben Ari",
            purpose=optional_string(params, "purpose") or "",
        )
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body=body,
            event=event,
        )
    body, err = create_scouting_mission(
        candidate_name=candidate_name or "Ron Ben Ari",
        purpose=optional_string(params, "purpose") or "",
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
    from lineup_store import finalize_lineup  # noqa: E402

    if is_write_denied(event):
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body={"status": "CANCELLED", "message": "Lineup save cancelled."},
            event=event,
        )
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=action_group,
            function_name=function_name,
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
            action_group=action_group,
            function_name=function_name,
            body={"status": "REJECTED", "message": err},
            event=event,
        )
    return build_function_response(
        action_group=action_group,
        function_name=function_name,
        body=record or {"status": "FAILURE"},
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
