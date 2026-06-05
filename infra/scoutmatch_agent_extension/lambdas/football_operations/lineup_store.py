"""Lineup persistence and validation."""

from __future__ import annotations

import json

from operations_store import get_item, put_item
from squad_context import get_current_context
from validation import normalize_name, resolve_squad_player, validate_formation, validate_starter_lineup


def get_current_lineup() -> dict | None:
    return get_item("lineup#current")


def parse_starting_xi(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    players = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, pos = chunk.split(":", 1)
        players.append({"name": name.strip(), "position": pos.strip().upper()})
    return players


def finalize_lineup(params: dict) -> tuple[dict | None, str]:
    ctx = get_current_context()
    if not ctx:
        return None, "Save the squad planning context before finalizing a lineup."

    formation = (params.get("formation") or ctx.get("preferred_formation") or "").strip()
    if not validate_formation(formation):
        return None, f"Unsupported formation: {formation or 'missing'}"

    starters = parse_starting_xi(params.get("starting_xi") or "")
    ok, err = validate_starter_lineup(starters)
    if not ok:
        return None, err

    enriched = []
    for starter in starters:
        squad = resolve_squad_player(starter["name"]) or {}
        status = "AVAILABLE"
        selection = get_item(f"player_selection#{normalize_name(starter['name'])}")
        if selection and selection.get("approval_status") == "PENDING_MANAGEMENT_APPROVAL":
            status = "PENDING_MANAGEMENT_APPROVAL"
        enriched.append(
            {
                "name": squad.get("display_name", starter["name"]),
                "position": starter["position"],
                "status": status,
            }
        )

    record = put_item(
        entity_key="lineup#current",
        item_type="LINEUP",
        payload={
            "lineup_id": "current",
            "planning_context_id": ctx.get("planning_context_id"),
            "formation": formation,
            "opponent": ctx.get("opponent", ""),
            "starting_xi": enriched,
            "bench": params.get("bench") or "",
        },
    )
    return record, ""
