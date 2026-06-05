"""Lineup persistence and validation."""

from __future__ import annotations

import json

from demo_roster import build_demo_starting_xi, is_demo_lineup_request
from operations_store import active_demo_season_id, get_item, put_item
from squad_context import get_current_context
from validation import (
    normalize_name,
    resolve_squad_player,
    validate_formation,
    validate_starter_lineup,
)


def get_current_lineup() -> dict | None:
    record = get_item("lineup#current")
    if not record:
        return None
    season = (record.get("demo_season_id") or "").strip()
    if season and season != active_demo_season_id():
        return None
    return record


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
        return None, "Save the match planning context before finalizing a lineup."

    formation = (params.get("formation") or ctx.get("preferred_formation") or "").strip()
    if not validate_formation(formation):
        return None, f"Unsupported formation: {formation or 'missing'}"

    demo_mode = is_demo_lineup_request(params)
    raw_xi = (params.get("lineup_json") or params.get("starting_xi") or "").strip()
    if demo_mode and (not raw_xi or raw_xi.lower() in {"demo", "demo_lineup", "use_demo_roster", "demo roster"}):
        starters = build_demo_starting_xi(ron_at_right_back=True)
    else:
        starters = parse_starting_xi(raw_xi)
        if demo_mode and len(starters) < 11:
            starters = build_demo_starting_xi(ron_at_right_back=True)
    if not demo_mode and not starters:
        return None, (
            "Starting lineup is incomplete. Provide all 11 starters explicitly, "
            "or request the demo lineup if you want the sanitized 4-3-3 template."
        )
    allowed_external: frozenset[str] = frozenset()
    if demo_mode:
        allowed_external = frozenset(
            normalize_name(p["name"])
            for p in starters
            if not resolve_squad_player(p.get("name", ""))
        )
    ok, err = validate_starter_lineup(starters, allowed_external=allowed_external)
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
            "demo_season_id": active_demo_season_id(),
            "formation": formation,
            "opponent": (params.get("opponent") or ctx.get("opponent") or "").strip(),
            "starting_xi": enriched,
            "bench": params.get("bench") or "",
        },
    )
    return {
        **record,
        "status": "PENDING_HEAD_COACH_REVIEW",
        "lineup_state": "PROPOSED_LINEUP",
        "starting_players": 11,
    }, ""
