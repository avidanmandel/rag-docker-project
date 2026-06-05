"""Operational budget ledger helpers."""

from __future__ import annotations

import uuid

from operations_store import active_demo_season_id, get_item, list_by_prefix, put_item


def get_context_budget() -> dict | None:
    return get_item("squad_context#current")


def _in_active_demo_season(record: dict) -> bool:
    season = (record.get("demo_season_id") or "").strip()
    if not season:
        return False
    return season == active_demo_season_id()


def _active_planning_context_id() -> str:
    ctx = get_context_budget() or {}
    return str(ctx.get("planning_context_id") or "").strip()


def _reservation_in_context(entry: dict, active_ctx: str) -> bool:
    if not active_ctx:
        return True
    entry_ctx = str(entry.get("planning_context_id") or "").strip()
    if entry_ctx:
        return entry_ctx == active_ctx
    candidate = str(entry.get("candidate_name") or "").strip().lower()
    if not candidate:
        return False
    selection = get_item(f"player_selection#{candidate}")
    if not selection or not _in_active_demo_season(selection):
        return False
    selection_ctx = str(selection.get("planning_context_id") or "").strip()
    return not selection_ctx or selection_ctx == active_ctx


def sum_reserved_amounts(*, planning_context_id: str | None = None) -> int:
    active_ctx = (planning_context_id or _active_planning_context_id()).strip()
    total = 0
    for entry in list_by_prefix("budget_ledger#"):
        if entry.get("entry_type") != "RESERVATION":
            continue
        if not _in_active_demo_season(entry):
            continue
        if not _reservation_in_context(entry, active_ctx):
            continue
        total += int(entry.get("reserved_amount_eur") or 0)
    return total


def available_budget_from_context(*, planning_context_id: str | None = None) -> tuple[int | None, str]:
    ctx = get_context_budget()
    if not ctx:
        return None, "Squad planning context is missing. Save the current plan first."
    base = int(ctx.get("available_budget_eur") or 0)
    active_ctx = (planning_context_id or _active_planning_context_id()).strip() or None
    reserved = sum_reserved_amounts(planning_context_id=active_ctx)
    return max(base - reserved, 0), ""


def existing_selection_reservation(candidate_name: str) -> dict | None:
    key = f"player_selection#{candidate_name.strip().lower()}"
    record = get_item(key)
    active_ctx = _active_planning_context_id()
    if (
        record
        and record.get("reservation_status") == "RESERVED_PENDING_APPROVAL"
        and _in_active_demo_season(record)
    ):
        record_ctx = str(record.get("planning_context_id") or "").strip()
        if active_ctx and record_ctx != active_ctx:
            return None
        return record
    return None


def record_reservation(
    *,
    candidate_name: str,
    target_role: str,
    salary_eur: int,
    budget_before: int,
    reserved_amount: int,
    remaining_after: int,
    idempotency_key: str,
) -> dict:
    planning_context_id = _active_planning_context_id()
    selection = put_item(
        entity_key=f"player_selection#{candidate_name.strip().lower()}",
        item_type="PLAYER_SELECTION",
        payload={
            "candidate_name": candidate_name,
            "target_role": target_role,
            "salary_request_eur": salary_eur,
            "budget_before_eur": budget_before,
            "reserved_amount_eur": reserved_amount,
            "remaining_budget_eur": remaining_after,
            "reservation_status": "RESERVED_PENDING_APPROVAL",
            "approval_status": "PENDING_MANAGEMENT_APPROVAL",
            "idempotency_key": idempotency_key,
            "planning_context_id": planning_context_id,
        },
    )
    put_item(
        entity_key=f"budget_ledger#{uuid.uuid4().hex[:12]}",
        item_type="BUDGET_LEDGER",
        payload={
            "entry_type": "RESERVATION",
            "candidate_name": candidate_name,
            "reserved_amount_eur": reserved_amount,
            "status": "RESERVED_PENDING_APPROVAL",
            "idempotency_key": idempotency_key,
            "planning_context_id": planning_context_id,
        },
    )
    return selection
