"""Squad planning context operations."""

from __future__ import annotations

import uuid

from operations_store import get_item, put_item


def get_current_context() -> dict | None:
    return get_item("squad_context#current")


def update_context(params: dict) -> tuple[dict | None, str]:
    existing = get_current_context() or {}
    required_missing = []
    opponent = (params.get("opponent") or existing.get("opponent") or "").strip()
    formation = (params.get("preferred_formation") or existing.get("preferred_formation") or "").strip()
    if not opponent:
        required_missing.append("opponent")
    if not formation:
        required_missing.append("preferred_formation")
    if required_missing:
        return None, f"Missing required planning fields: {', '.join(required_missing)}"

    planning_context_id = existing.get("planning_context_id") or f"ctx-{uuid.uuid4().hex[:10]}"
    record = put_item(
        entity_key="squad_context#current",
        item_type="SQUAD_CONTEXT",
        payload={
            "planning_context_id": planning_context_id,
            "opponent": opponent,
            "preferred_formation": formation,
            "priority_positions": (params.get("priority_positions") or "").strip(),
            "strong_positions": (params.get("strong_positions") or "").strip(),
            "available_budget_eur": int(params.get("available_budget_eur") or existing.get("available_budget_eur") or 0),
            "immediate_starter_required": str(params.get("immediate_starter_required", "false")).lower()
            in {"1", "true", "yes"},
            "coach_notes": (params.get("coach_notes") or "").strip(),
        },
    )
    return record, ""
