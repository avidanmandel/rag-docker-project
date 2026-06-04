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
_WORKFLOW_REF_PREFIX = "workflow#"

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
    if os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}:
        return True
    return not STATE_MACHINE_ARN.strip()


def _workflow_ref_key(ref: str) -> str:
    return f"{_WORKFLOW_REF_PREFIX}{ref}"


def _persist_workflow_ref(ref: str, payload: dict) -> None:
    if _use_local():
        return
    try:
        import boto3

        safe = {k: v for k, v in payload.items() if k != "execution_arn"}
        item = {
            "candidate_key": _workflow_ref_key(ref),
            "review_json": json.dumps(safe),
            "updated_at": _now(),
        }
        if payload.get("execution_arn"):
            item["execution_arn"] = payload["execution_arn"]
        boto3.resource("dynamodb").Table(REVIEWS_TABLE).put_item(Item=item)
    except Exception:
        return


def _load_workflow_ref(ref: str) -> dict | None:
    if ref in _LOCAL_STATUS:
        return _LOCAL_STATUS[ref]
    if _use_local():
        return None
    try:
        import boto3

        item = (
            boto3.resource("dynamodb")
            .Table(REVIEWS_TABLE)
            .get_item(Key={"candidate_key": _workflow_ref_key(ref)})
            .get("Item")
        )
    except Exception:
        return None
    if not item:
        return None
    payload = json.loads(item.get("review_json") or "{}")
    if item.get("execution_arn"):
        payload["execution_arn"] = item["execution_arn"]
    _LOCAL_STATUS[ref] = payload
    return payload


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
    raw = target_role.strip().lower().replace(" ", "-")
    if "right" in raw and "back" in raw:
        return "right-back"
    if "striker" in raw or "below" in raw:
        return "below-striker"
    if "forward" in raw:
        return "forward"
    return raw


def _build_sf_input(params: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    target_role = require_string(params, "target_role")
    salary = require_int(params, "candidate_salary_eur")
    committed = require_int(params, "current_committed_salary_eur")
    immediate = require_bool(params, "immediate_starter")
    normalized = _normalize_role(target_role)
    budget_parameters = [
        {"name": "candidate_name", "value": candidate_name},
        {"name": "candidate_annual_salary_eur", "value": str(salary)},
        {"name": "current_committed_salary_eur", "value": str(committed)},
        {"name": "immediate_starter", "value": str(immediate).lower()},
    ]
    payload: dict = {
        "candidate_name": candidate_name,
        "target_role": target_role,
        "target_role_normalized": normalized,
        "candidate_key": candidate_name.strip().lower().replace(" ", "-"),
        "budgetParameters": budget_parameters,
        "updated_at": _now(),
    }
    if normalized == "right-back":
        payload["rightBackPayload"] = bedrock_action_event(
            action_group="ScoutMatchRightBackActionsAvidan",
            function_name="EvaluateRightBackFit",
            parameters={
                "candidate_name": candidate_name,
                "available_immediately": immediate,
                "preferred_foot": "right",
                "tactical_summary": "documented in club scouting notes",
                "budget_info": f"{salary},{committed}",
            },
        )
    elif normalized == "below-striker":
        payload["belowStrikerPayload"] = bedrock_action_event(
            action_group="ScoutMatchBelowStrikerActionsAvidan",
            function_name="EvaluateBelowStrikerFit",
            parameters={
                "candidate_name": candidate_name,
                "position": "attacking midfielder",
                "skill_scores": "vision:good,creativity:good,key_passing:good",
                "available_immediately": immediate,
                "budget_info": f"{salary},{committed}",
            },
        )
    elif normalized == "forward":
        payload["forwardPayload"] = bedrock_action_event(
            action_group="ScoutMatchForwardActionsAvidan",
            function_name="EvaluateForwardFit",
            parameters={
                "candidate_name": candidate_name,
                "forward_profile": "documented link-up and movement",
                "annual_salary_eur": salary,
                "current_committed_salary_eur": committed,
                "exception_approved": False,
            },
        )
    return payload


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

    sf_input = _build_sf_input(params)
    if sf_input["target_role_normalized"] not in ROLE_BRANCHES:
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="StartCandidateReviewWorkflow",
            body={"status": "REJECTED", "message": "Unsupported target_role for workflow."},
            event=event,
        )
    client = boto3.client("stepfunctions")
    execution = client.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps(sf_input),
    )
    ref = sanitize_workflow_reference(execution["executionArn"])
    _LOCAL_STATUS[ref] = {
        "status": "RUNNING",
        "execution_arn": execution["executionArn"],
        "candidate_name": sf_input["candidate_name"],
        "target_role": sf_input["target_role_normalized"],
    }
    _persist_workflow_ref(ref, _LOCAL_STATUS[ref])
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name="StartCandidateReviewWorkflow",
        body={"status": "STARTED", "workflow_reference": ref, "workflow_status": "RUNNING"},
        event=event,
    )


def _parse_lambda_invoke_result(result: dict) -> dict:
    try:
        payload = result.get("Payload")
        if isinstance(payload, bytes):
            payload = payload.decode()
        if isinstance(payload, str):
            payload = json.loads(payload)
        return parse_function_body(payload if isinstance(payload, dict) else {})
    except (TypeError, json.JSONDecodeError):
        return {}


def _finalize_execution(ref: str, output: dict, meta: dict) -> dict:
    budget_body = _parse_lambda_invoke_result(output.get("budgetResult", {}))
    tactical_body = _parse_lambda_invoke_result(output.get("tacticalResult", {}))
    recommendation = "PROCEED" if (
        budget_body.get("decision") in {"PASS", "NEEDS_EXCEPTION"}
        and tactical_body.get("decision") in {"PASS", "NEEDS_EXCEPTION", "PASS_WITH_NOTES"}
    ) else "DO_NOT_PROCEED"
    review = {
        "candidate_name": meta.get("candidate_name", ""),
        "target_role": meta.get("target_role", ""),
        "workflow_status": "SUCCEEDED",
        "budget_decision": budget_body.get("decision"),
        "tactical_decision": tactical_body.get("decision"),
        "final_recommendation": recommendation,
        "updated_at": _now(),
    }
    key = review["candidate_name"].strip().lower()
    if not _use_local() and REVIEWS_TABLE:
        import boto3

        boto3.resource("dynamodb").Table(REVIEWS_TABLE).put_item(
            Item={
                "candidate_key": key,
                "review_json": json.dumps(review),
                "updated_at": review["updated_at"],
            }
        )
    _LOCAL_REVIEWS[key] = review
    _persist_workflow_ref(ref, {"status": "SUCCEEDED", "review": review})
    brief_event = bedrock_action_event(
        action_group="ScoutMatchRecruitmentBriefActionsAvidan",
        function_name="CreateRecruitmentBrief",
        parameters={
            "candidate_name": review["candidate_name"],
            "target_role": review["target_role"],
            "tactical_decision": str(tactical_body.get("decision", "UNKNOWN")),
            "budget_decision": str(budget_body.get("decision", "UNKNOWN")),
            "missing_information": "",
        },
        session_attributes={"workflow_internal": "true", "write_confirmed": "true"},
    )
    try:
        _invoke_lambda("ScoutMatchRecruitmentBriefAvidan", brief_event)
    except Exception:
        pass
    return review


def _status(params: dict, event: dict) -> dict:
    ref = require_string(params, "workflow_reference")
    payload = _load_workflow_ref(ref)
    if payload:
        if payload.get("status") in {"SUCCEEDED", "FAILED"}:
            return build_function_response(
                action_group=ACTION_GROUP,
                function_name="GetCandidateReviewWorkflowStatus",
                body={
                    "workflow_reference": ref,
                    "workflow_status": payload.get("status", "UNKNOWN"),
                    "final_recommendation": payload.get("review", {}).get("final_recommendation"),
                },
                event=event,
            )
        if payload.get("status") == "RUNNING" and payload.get("execution_arn"):
            import boto3

            client = boto3.client("stepfunctions")
            try:
                desc = client.describe_execution(executionArn=payload["execution_arn"])
            except Exception:
                desc = {"status": "RUNNING"}
            status = desc.get("status", "RUNNING")
            if status == "SUCCEEDED":
                try:
                    output = json.loads(desc.get("output") or "{}")
                except json.JSONDecodeError:
                    output = {}
                review = _finalize_execution(ref, output, payload)
                payload = {"status": "SUCCEEDED", "review": review}
                _LOCAL_STATUS[ref] = payload
                _persist_workflow_ref(ref, payload)
            elif status in {"FAILED", "TIMED_OUT", "ABORTED"}:
                payload = {"status": "FAILED"}
                _LOCAL_STATUS[ref] = payload
                _persist_workflow_ref(ref, payload)
        return build_function_response(
            action_group=ACTION_GROUP,
            function_name="GetCandidateReviewWorkflowStatus",
            body={
                "workflow_reference": ref,
                "workflow_status": payload.get("status", "UNKNOWN"),
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
            "message": "Workflow reference not found.",
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
