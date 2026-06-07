"""SubmitCriticalDecisionAndSendEmail workflow."""

from __future__ import annotations

import hashlib
import uuid

from budget_ledger import (
    available_budget_from_context,
    ensure_demo_context,
    existing_selection_reservation,
    get_context_budget,
    record_reservation,
    sum_reserved_amounts,
)
from budget_rules import evaluate_budget
from operations_store import active_demo_season_id, put_item
from ses_adapter import send_review_email
from validation import normalize_name, resolve_transfer_candidate


def _idempotency_key(candidate_name: str, ctx_id: str) -> str:
    return hashlib.sha256(f"critical:{candidate_name}:{ctx_id}".encode()).hexdigest()[:16]


def prepare_critical_decision(
    *,
    candidate_name: str,
    target_role: str = "",
    salary_eur: int | None = None,
    decision_type: str = "recruitment",
) -> dict:
    ctx = get_context_budget() or ensure_demo_context()
    candidate = resolve_transfer_candidate(candidate_name)
    if not candidate:
        return {
            "status": "FAILURE",
            "message": f"Candidate '{candidate_name}' is not grounded in approved ScoutMatch records.",
        }
    role = (target_role or candidate.get("target_role") or "").strip()
    salary = int(salary_eur if salary_eur is not None else candidate["salary_eur"])
    available, err = available_budget_from_context()
    if err:
        return {"status": "FAILURE", "message": err}
    return {
        "status": "PENDING_CONFIRMATION",
        "confirmation_required": True,
        "decision_type": decision_type,
        "candidate_name": candidate["display_name"],
        "target_role": role,
        "candidate_cost_eur": salary,
        "salary_eur": salary,
        "available_budget_eur": int(available or 0),
        "message": (
            f"Confirm submitting {candidate['display_name']} for management review. "
            "No budget will be reserved until you confirm."
        ),
        "user_boundary": "No transfer has been approved. Management review is still required.",
    }


def deny_critical_decision() -> dict:
    return {
        "status": "CANCELLED",
        "message": (
            "The recommendation was cancelled. No budget was reserved. "
            "No management-review item was created. No email was sent."
        ),
    }


def submit_critical_decision(
    *,
    candidate_name: str,
    target_role: str = "",
    salary_eur: int | None = None,
    decision_type: str = "recruitment",
    selection_reason: str = "",
) -> tuple[dict | None, str]:
    ctx = get_context_budget() or ensure_demo_context()
    if not ctx:
        return None, "Save planning context before submitting a critical decision."
    candidate = resolve_transfer_candidate(candidate_name)
    if not candidate:
        return None, f"Candidate '{candidate_name}' is not grounded in approved ScoutMatch records."
    role = (target_role or candidate.get("target_role") or "").strip()
    salary = int(salary_eur if salary_eur is not None else candidate["salary_eur"])
    ctx_id = str(ctx.get("planning_context_id") or "current")
    idem = _idempotency_key(candidate["display_name"], ctx_id)
    entity_key = f"critical_decision#{normalize_name(candidate['display_name'])}"
    existing = existing_selection_reservation(candidate["display_name"])
    if existing and existing.get("idempotency_key") == idem:
        email = send_review_email(existing)
        return {
            "status": "PENDING_MANAGEMENT_APPROVAL",
            "candidate_name": candidate["display_name"],
            "target_role": existing.get("target_role", role),
            "reserved_amount_eur": existing.get("reserved_amount_eur"),
            "remaining_budget_eur": existing.get("remaining_budget_eur"),
            "email_delivery_status": email.get("mode"),
            "email_user_message": email.get("user_message"),
            "idempotent": True,
            "user_boundary": "No transfer has been approved. Management review is still required.",
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
            "candidate_name": candidate["display_name"],
            "message": "; ".join(budget_body.get("reasons") or ["Selection exceeds budget rules."]),
        }, ""
    budget_before = int(available or 0)
    if salary > budget_before:
        return {
            "status": "REJECTED",
            "candidate_name": candidate["display_name"],
            "message": "Insufficient operational budget for this reservation.",
        }, ""
    remaining = budget_before - salary
    selection = record_reservation(
        candidate_name=candidate["display_name"],
        target_role=role,
        salary_eur=salary,
        budget_before=budget_before,
        reserved_amount=salary,
        remaining_after=remaining,
        idempotency_key=idem,
    )
    record = {
        **selection,
        "decision_id": str(uuid.uuid4()),
        "decision_type": decision_type,
        "candidate_cost_eur": salary,
        "status": "PENDING_MANAGEMENT_APPROVAL",
        "review_target": "management",
        "demo_scope": active_demo_season_id(),
        "planning_context_id": ctx_id,
        "entity_key": entity_key,
    }
    if selection_reason:
        record["selection_reason"] = selection_reason[:500]
    put_item(entity_key=entity_key, item_type="CRITICAL_DECISION_REVIEW", payload=record)
    put_item(
        entity_key=selection["entity_key"],
        item_type="PLAYER_SELECTION",
        payload={k: v for k, v in selection.items() if k not in {"entity_key", "item_type"}},
    )
    email = send_review_email(record)
    record["email_delivery_status"] = email.get("mode")
    put_item(entity_key=entity_key, item_type="CRITICAL_DECISION_REVIEW", payload=record)
    return {
        "status": "PENDING_MANAGEMENT_APPROVAL",
        "candidate_name": candidate["display_name"],
        "target_role": role,
        "reserved_amount_eur": salary,
        "remaining_budget_eur": remaining,
        "email_delivery_status": email.get("mode"),
        "email_user_message": email.get("user_message"),
        "idempotent": False,
        "user_boundary": "No transfer has been approved. Management review is still required.",
    }, ""
