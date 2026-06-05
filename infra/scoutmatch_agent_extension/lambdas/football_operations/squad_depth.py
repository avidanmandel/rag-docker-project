"""Optional squad depth gap analysis (internal helper)."""

from __future__ import annotations

from budget_ledger import available_budget_from_context
from lineup_store import get_current_lineup
from operations_store import list_by_prefix
from squad_context import get_current_context


def analyze_depth_gaps() -> dict:
    ctx = get_current_context() or {}
    lineup = get_current_lineup() or {}
    starters = lineup.get("starting_xi") or []
    covered = {p.get("position") for p in starters}
    priority = [p.strip() for p in (ctx.get("priority_positions") or "").split(",") if p.strip()]
    unavailable = {
        item.get("affected_position")
        for item in list_by_prefix("availability#")
        if item.get("availability_status") == "UNAVAILABLE"
    }
    gaps = []
    for pos in priority:
        if pos not in covered:
            gaps.append({"position": pos, "issue": "missing_in_current_lineup"})
        elif pos in unavailable:
            gaps.append({"position": pos, "issue": "starter_unavailable"})
    remaining, _ = available_budget_from_context()
    return {
        "priority_positions": priority,
        "gaps": gaps,
        "remaining_budget_eur": remaining,
        "assumption_note": "Analysis uses DynamoDB operational state only; no invented players.",
    }
