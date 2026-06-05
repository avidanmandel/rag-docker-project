"""Submit player selection using shared budget module (no Lambda invoke)."""

from __future__ import annotations

import hashlib

from budget_ledger import (
    available_budget_from_context,
    existing_selection_reservation,
    get_context_budget,
    record_reservation,
    sum_reserved_amounts,
)
from budget_rules import evaluate_budget
from sns_notification import publish_management_notification
from validation import resolve_transfer_candidate


def submit_selection(
    candidate_name: str,
    *,
    target_role: str = "",
    salary_eur: int | None = None,
    selection_reason: str = "",
) -> tuple[dict | None, str]:
    ctx = get_context_budget()
    if not ctx:
        return None, "Save the match planning context before submitting a player selection."

    candidate = resolve_transfer_candidate(candidate_name)
    if not candidate:
        return None, f"Candidate '{candidate_name}' is not grounded in approved ScoutMatch records."

    role = (target_role or candidate.get("target_role") or "").strip()
    salary = int(salary_eur if salary_eur is not None else candidate["salary_eur"])
    if salary <= 0:
        return None, "A valid salary_eur is required and must come from approved ScoutMatch records."

    idempotency_key = hashlib.sha256(
        f"{candidate['display_name']}:{ctx.get('planning_context_id', 'current')}".encode()
    ).hexdigest()[:16]

    existing = existing_selection_reservation(candidate["display_name"])
    if existing and existing.get("idempotency_key") == idempotency_key:
        return {
            "status": "PENDING_MANAGEMENT_APPROVAL",
            "selected_player": candidate["display_name"],
            "target_role": existing.get("target_role", role),
            "reserved_amount_eur": existing.get("reserved_amount_eur"),
            "remaining_budget_eur": existing.get("remaining_budget_eur"),
            "management_notified": True,
            "idempotent": True,
        }, ""

    available, err = available_budget_from_context()
    if err:
        return None, err
    committed = sum_reserved_amounts()
    budget_body = evaluate_budget(
        candidate_name=candidate["display_name"],
        candidate_salary=salary,
        committed_before=committed,
        immediate_starter=True,
    )
    decision = budget_body.get("decision", "FAIL")
    if decision not in {"PASS", "NEEDS_EXCEPTION"}:
        return {
            "status": "REJECTED",
            "selected_player": candidate["display_name"],
            "budget_decision": decision,
            "message": "; ".join(budget_body.get("reasons") or ["Selection exceeds budget rules."]),
        }, ""

    budget_before = int(available or 0)
    if salary > budget_before:
        return {
            "status": "REJECTED",
            "selected_player": candidate["display_name"],
            "budget_decision": "FAIL",
            "message": "Insufficient operational budget for this reservation.",
        }, ""

    remaining = budget_before - salary
    selection = record_reservation(
        candidate_name=candidate["display_name"],
        target_role=role or candidate["target_role"],
        salary_eur=salary,
        budget_before=budget_before,
        reserved_amount=salary,
        remaining_after=remaining,
        idempotency_key=idempotency_key,
    )
    if selection_reason:
        selection["selection_reason"] = selection_reason[:500]
    sns_result = publish_management_notification(selection, decision)
    return {
        "status": "PENDING_MANAGEMENT_APPROVAL",
        "selected_player": candidate["display_name"],
        "target_role": role or candidate["target_role"],
        "reserved_amount_eur": salary,
        "remaining_budget_eur": remaining,
        "management_notified": bool(sns_result.get("published")),
        "budget_decision": decision,
        "sns": sns_result,
        "idempotent": False,
    }, ""
