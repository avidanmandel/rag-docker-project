"""Submit player selection to management."""

from __future__ import annotations

import hashlib
import json
import os
import sys

from budget_ledger import (
    available_budget_from_context,
    existing_selection_reservation,
    get_context_budget,
    record_reservation,
    sum_reserved_amounts,
)
from sns_notification import publish_management_notification
from validation import resolve_transfer_candidate

_LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
_COMMON = os.path.join(_LAMBDA_ROOT, os.pardir, "common")
if _COMMON not in sys.path:
    sys.path.insert(0, os.path.normpath(_COMMON))

from stepfn_adapter import bedrock_action_event, parse_function_body  # noqa: E402


def _invoke_budget(candidate_name: str, salary: int, committed: int) -> dict:
    event = bedrock_action_event(
        action_group="ScoutMatchBudgetActionsAvidan",
        function_name="CalculateBudgetImpact",
        parameters={
            "candidate_name": candidate_name,
            "candidate_annual_salary_eur": salary,
            "current_committed_salary_eur": committed,
            "immediate_starter": True,
            "exception_justification": "",
        },
    )
    if os.getenv("SCOUTMATCH_WORKFLOW_INPROCESS", "").lower() in {"1", "true", "yes"}:
        import importlib.util

        path = os.path.normpath(os.path.join(_LAMBDA_ROOT, os.pardir, "budget_impact", "lambda_function.py"))
        spec = importlib.util.spec_from_file_location("budget_impact", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return parse_function_body(module.lambda_handler(event, None))
    import boto3

    resp = boto3.client("lambda").invoke(
        FunctionName="ScoutMatchBudgetImpactAvidan",
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode("utf-8"),
    )
    return parse_function_body(json.loads(resp["Payload"].read()))


def submit_selection(candidate_name: str, selection_reason: str = "") -> tuple[dict | None, str]:
    ctx = get_context_budget()
    if not ctx:
        return None, "Save the squad planning context before submitting a player selection."

    candidate = resolve_transfer_candidate(candidate_name)
    if not candidate:
        return None, f"Candidate '{candidate_name}' is not grounded in approved ScoutMatch records."

    idempotency_key = hashlib.sha256(
        f"{candidate['display_name']}:{ctx.get('planning_context_id', 'current')}".encode()
    ).hexdigest()[:16]

    existing = existing_selection_reservation(candidate["display_name"])
    if existing and existing.get("idempotency_key") == idempotency_key:
        return {
            "status": "ALREADY_RESERVED",
            "candidate_name": candidate["display_name"],
            "reservation_status": existing.get("reservation_status"),
            "approval_status": existing.get("approval_status"),
            "remaining_budget_eur": existing.get("remaining_budget_eur"),
            "idempotent": True,
        }, ""

    available, err = available_budget_from_context()
    if err:
        return None, err
    salary = int(candidate["salary_eur"])
    committed = sum_reserved_amounts()
    budget_body = _invoke_budget(candidate["display_name"], salary, committed)
    decision = budget_body.get("decision", "FAIL")
    if decision not in {"PASS", "NEEDS_EXCEPTION"}:
        return {
            "status": "REJECTED",
            "candidate_name": candidate["display_name"],
            "budget_decision": decision,
            "message": budget_body.get("missing_information")
            or "Selection exceeds the current operational budget rules.",
        }, ""

    budget_before = int(available or 0)
    if salary > budget_before:
        return {
            "status": "REJECTED",
            "candidate_name": candidate["display_name"],
            "budget_decision": "FAIL",
            "message": "Insufficient operational budget for this reservation.",
        }, ""

    remaining = budget_before - salary
    selection = record_reservation(
        candidate_name=candidate["display_name"],
        target_role=candidate["target_role"],
        salary_eur=salary,
        budget_before=budget_before,
        reserved_amount=salary,
        remaining_after=remaining,
        idempotency_key=idempotency_key,
    )
    if selection_reason:
        selection["selection_reason"] = selection_reason
    sns_result = publish_management_notification(selection, decision)
    return {
        "status": "RESERVED",
        "candidate_name": candidate["display_name"],
        "target_role": candidate["target_role"],
        "salary_request_eur": salary,
        "budget_before_eur": budget_before,
        "reserved_amount_eur": salary,
        "remaining_budget_eur": remaining,
        "reservation_status": "RESERVED_PENDING_APPROVAL",
        "approval_status": "PENDING_MANAGEMENT_APPROVAL",
        "budget_decision": decision,
        "sns": sns_result,
        "idempotent": False,
    }, ""
