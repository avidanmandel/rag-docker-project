"""Optional player availability updates (internal helper)."""

from __future__ import annotations

from operations_store import put_item
from validation import normalize_name, resolve_squad_player


def record_availability_change(player_name: str, availability_status: str, reason: str = "") -> tuple[dict | None, str]:
    squad = resolve_squad_player(player_name)
    if not squad:
        return None, f"Unknown squad player: {player_name}"
    record = put_item(
        entity_key=f"availability#{normalize_name(player_name)}",
        item_type="AVAILABILITY_UPDATE",
        payload={
            "player_name": squad["display_name"],
            "availability_status": availability_status.strip().upper(),
            "reason": reason.strip(),
            "affected_position": squad.get("position", ""),
        },
    )
    return record, ""
