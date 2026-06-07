"""SubmitCriticalDecisionAndSendEmail — legacy SubmitPlayerSelectionToManagement when v2 disabled."""

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

V2_ACTION_GROUP = "ScoutMatchCritDecisionAvidan"
V2_FUNCTION = "SubmitCriticalDecisionAndSendEmail"
LEGACY_ACTION_GROUP = "ScoutMatchSelectionAgAvidan"
LEGACY_FUNCTION = "SubmitPlayerSelectionToManagement"


def _config():
    if business_workflow_v2_enabled():
        return V2_ACTION_GROUP, V2_FUNCTION
    return LEGACY_ACTION_GROUP, LEGACY_FUNCTION


def _handle_v2(params: dict, event: dict, action_group: str, function_name: str) -> dict:
    from critical_decision import (  # noqa: E402
        deny_critical_decision,
        prepare_critical_decision,
        submit_critical_decision,
    )

    if is_write_denied(event):
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body=deny_critical_decision(),
            event=event,
        )
    if not is_write_confirmed(event):
        body = prepare_critical_decision(
            candidate_name=require_string(params, "candidate_name"),
            target_role=optional_string(params, "target_role") or "",
            salary_eur=optional_int(params, "salary_eur"),
            decision_type=optional_string(params, "decision_type") or "recruitment",
        )
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body=body,
            event=event,
        )
    body, err = submit_critical_decision(
        candidate_name=require_string(params, "candidate_name"),
        target_role=optional_string(params, "target_role") or "",
        salary_eur=optional_int(params, "salary_eur"),
        decision_type=optional_string(params, "decision_type") or "recruitment",
        selection_reason=optional_string(params, "selection_reason") or "",
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
    from player_selection import submit_selection  # noqa: E402

    if is_write_denied(event):
        return build_function_response(
            action_group=action_group,
            function_name=function_name,
            body={
                "status": "CANCELLED",
                "message": "Selection cancelled. No budget reserved.",
            },
            event=event,
        )
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=action_group,
            function_name=function_name,
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
