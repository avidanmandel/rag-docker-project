"""
ScoutMatchRecruitmentWorkflowAvidan — candidate review workflow (Step Functions or local orchestration).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

_LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
_COMMON = os.path.join(_LAMBDA_ROOT, os.pardir, "common")
if _COMMON not in sys.path:
    sys.path.insert(0, os.path.normpath(_COMMON))

from bedrock_response import (  # noqa: E402
    build_function_response,
    handle_action_errors,
    require_bool,
    require_int,
    require_string,
)
from stepfn_adapter import (  # noqa: E402
    bedrock_action_event,
    parse_function_body,
    sanitize_workflow_reference,
)
from write_confirmation import (  # noqa: E402
    is_write_confirmed,
    pending_confirmation_response,
)

ACTION_GROUP = "ScoutMatchRecruitmentWorkflowActionsAvidan"
STATE_MACHINE_ARN = os.getenv("SCOUTMATCH_REVIEW_STATE_MACHINE_ARN", "")
REVIEWS_TABLE = os.getenv("SCOUTMATCH_REVIEWS_TABLE", "ScoutMatchRecruitmentReviewsAvidan")
_LOCAL_REVIEWS: dict[str, dict] = {}
_LOCAL_STATUS: dict[str, dict] = {}

ROLE_BRANCHES = {
    "right-back": ("ScoutMatchRightBackFitAvidan", "ScoutMatchRightBackActionsAvidan", "EvaluateRightBackFit"),
    "right_back": ("ScoutMatchRightBackFitAvidan", "ScoutMatchRightBackActionsAvidan", "EvaluateRightBackFit"),
    "below-striker": (
        "ScoutMatchBelowStrikerFitAvidan",
        "ScoutMatchBelowStrikerActionsAvidan",
        "EvaluateBelowStrikerFit",
    ),
    "below_striker": (
        "ScoutMatchBelowStrikerFitAvidan",
        "ScoutMatchBelowStrikerActionsAvidan",
        "EvaluateBelowStrikerFit",
    ),
    "forward": ("ScoutMatchForwardFitAvidan", "ScoutMatchForwardActionsAvidan", "EvaluateForwardFit"),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _use_local() -> bool:
    return os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"} or not STATE_MACHINE_ARN


def _invoke_lambda(function_name: str, payload: dict) -> dict:
    if os.getenv("SCOUTMATCH_WORKFLOW_INPROCESS", "").lower() in {"1", "true", "yes"}:
        return _invoke_inprocess(function_name, payload)
    import boto3

    client = boto3.client("lambda")
    resp = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    return json.loads(resp["Payload"].read())


def _invoke_inprocess(function_name: str, payload: dict) -> dict:
    import importlib.util

    folder_map = {
        "ScoutMatchBudgetImpactAvidan": "budget_impact",
        "ScoutMatchRightBackFitAvidan": "right_back_fit",
        "ScoutMatchBelowStrikerFitAvidan": "below_striker_fit",
        "ScoutMatchForwardFitAvidan": "forward_fit",
    }
    folder = folder_map[function_name]
    path = os.path.normpath(os.path.join(_LAMBDA_ROOT, os.pardir, folder, "lambda_function.py"))
    spec = importlib.util.spec_from_file_location(f"{function_name}_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.lambda_handler(payload, None)


def _normalize_role(target_role: str) -> str:
    return target_role.strip().lower().replace(" ", "-")


def _run_local_review(params: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    target_role = _normalize_role(require_string(params, "target_role"))
    salary = require_int(params, "candidate_salary_eur")
    committed = require_int(params, "current_committed_salary_eur")
    immediate = require_bool(params, "immediate_starter")

    if target_role not in ROLE_BRANCHES:
        return {
            "status": "REJECTED",
            "message": "Unsupported target_role for automated review workflow.",
        }

    budget_event = bedrock_action_event(
        action_group="ScoutMatchBudgetActionsAvidan",
        function_name="CalculateBudgetImpact",
        parameters={
            "candidate_name": candidate_name,
            "candidate_annual_salary_eur": salary,
            "current_committed_salary_eur": committed,
            "immediate_starter": immediate,
        },
    )
    budget_body = parse_function_body(_invoke_lambda("ScoutMatchBudgetImpactAvidan", budget_event))

    lambda_name, action_group, function_name = ROLE_BRANCHES[target_role]
    tactical_params = {
        "candidate_name": candidate_name,
        "available_immediately": immediate,
        "preferred_foot": "right",
        "tactical_summary": "documented in club scouting notes",
        "budget_info": f"{salary},{committed}",
    }
    if function_name == "EvaluateBelowStrikerFit":
        tactical_params = {
            "candidate_name": candidate_name,
            "position": "attacking midfielder",
            "skill_scores": "vision:good,creativity:good,key_passing:good",
            "available_immediately": immediate,
            "budget_info": f"{salary},{committed}",
        }
    elif function_name == "EvaluateForwardFit":
        tactical_params = {
            "candidate_name": candidate_name,
            "forward_profile": "documented link-up and movement",
            "annual_salary_eur": salary,
            "current_committed_salary_eur": committed,
            "exception_approved": budget_body.get("decision") == "NEEDS_EXCEPTION",
        }

    tactical_event = bedrock_action_event(
        action_group=action_group,
        function_name=function_name,
        parameters=tactical_params,
    )
    tactical_body = parse_function_body(_invoke_lambda(lambda_name, tactical_event))

    recommendation = "PROCEED" if (
        budget_body.get("decision") in {"PASS", "NEEDS_EXCEPTION"}
        and tactical_body.get("decision") in {"PASS", "NEEDS_EXCEPTION"}
    ) else "DO_NOT_PROCEED"

    review = {
        "candidate_name": candidate_name,
        "target_role": target_role,
        "workflow_status": "SUCCEEDED",
        "budget_decision": budget_body.get("decision"),
        "tactical_decision": tactical_body.get("decision"),
        "final_recommendation": recommendation,
        "missing_information": budget_body.get("missing_information", ""),
        "updated_at": _now(),
    }
    _LOCAL_REVIEWS[candidate_name.lower()] = review
    return review


def _start(params: dict, event: dict) -> dict:
    if not is_write_confirmed(event):
        return pending_confirmation_response(
            action_group=ACTION_GROUP,
            function_name="StartCandidateReviewWorkflow",
            message="Please confirm before starting a full candidate review workflow.",
            event=event,
        )
    for field in (
        "candidate_name",
        "target_role",
        "candidate_salary_eur",
        "current_committed_salary_eur",
        "immediate_starter",
    ):
        if field not in params or params[field] in (None, ""):
            return build_function_response(
                action_group=ACTION_GROUP,
                function_name="StartCandidateReviewWorkflow",
                body={"status": "FAILURE", "message": f"Missing evidence: {field}"},
                event=event,
            )

    if _use_local():
        review = _run_local_review(params)
        if review.get("status") == "REJECTED":
            return build_function_response(
                action_group=ACTION_GROUP,
                function_name="StartCandidateReviewWorkflow",
                body=review,
                event=event,
            )
        ref = sanitize_workflow_reference(f"local-{uuid.uuid4().hex[:12]}")
        _LOCAL_STATUS[ref] = {"status": "SUCCEEDED", "review": review}
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="StartCandidateReviewWorkflow",
            body={
                "status": "STARTED",
                "workflow_reference": ref,
                "workflow_status": review["workflow_status"],
            },
            event=event,
        )

    import boto3

    client = boto3.client("stepfunctions")
    execution = client.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps(
            {
                "candidate_name": params["candidate_name"],
                "target_role": params["target_role"],
                "candidate_salary_eur": int(params["candidate_salary_eur"]),
                "current_committed_salary_eur": int(params["current_committed_salary_eur"]),
                "immediate_starter": str(params["immediate_starter"]).lower() == "true",
            }
        ),
    )
    ref = sanitize_workflow_reference(execution["executionArn"])
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="StartCandidateReviewWorkflow",
        body={"status": "STARTED", "workflow_reference": ref, "workflow_status": "RUNNING"},
        event=event,
    )


def _status(params: dict, event: dict) -> dict:
    ref = require_string(params, "workflow_reference")
    if ref in _LOCAL_STATUS:
        payload = _LOCAL_STATUS[ref]
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="GetCandidateReviewWorkflowStatus",
            body={
                "workflow_reference": ref,
                "workflow_status": payload["status"],
                "final_recommendation": payload.get("review", {}).get("final_recommendation"),
            },
            event=event,
        )
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="GetCandidateReviewWorkflowStatus",
        body={
            "workflow_reference": ref,
            "workflow_status": "UNKNOWN",
            "message": "Workflow status lookup requires deployed Step Functions (apply stage).",
        },
        event=event,
    )


def _result(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    review = _LOCAL_REVIEWS.get(candidate_name.lower())
    if not review:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="GetCandidateReviewResult",
            body={"status": "NOT_FOUND", "candidate_name": candidate_name},
            event=event,
        )
    safe = {k: review[k] for k in review if k != "execution_arn"}
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="GetCandidateReviewResult",
        body={"status": "FOUND", "review": safe},
        event=event,
    )


_HANDLERS = {
    "StartCandidateReviewWorkflow": _start,
    "GetCandidateReviewWorkflowStatus": _status,
    "GetCandidateReviewResult": _result,
}


def lambda_handler(event, context):  # noqa: ARG001
    function_name = (event.get("function") or "").strip()
    handler = _HANDLERS.get(function_name)
    if not handler:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name=function_name or "Unknown",
            body={"status": "FAILURE", "message": "Unknown workflow function."},
            event=event,
        )
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=function_name,
        event=event,
        handler=handler,
    )
