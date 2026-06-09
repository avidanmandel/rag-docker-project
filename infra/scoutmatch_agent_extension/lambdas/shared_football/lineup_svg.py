"""SVG lineup board generation."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone

from budget_ledger import available_budget_from_context
from lineup_store import get_current_lineup
from operations_store import active_demo_season_id, get_item, list_by_prefix, put_item
from validation import assign_formation_slots, normalize_name, slug_name

LINEUP_PREFIX = os.getenv(
    "SCOUTMATCH_LINEUP_S3_PREFIX", "scoutmatch/football-operations/lineups/"
)
BUCKET = os.getenv("SCOUTMATCH_LINEUP_BUCKET", os.getenv("SCOUTMATCH_BRIEF_BUCKET", ""))
_LOCAL_SVG: dict[str, str] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _short_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[-1] if parts else full_name


def _slot_positions(formation: str, starters: list[dict]) -> list[tuple[dict, float, float]]:
    return assign_formation_slots(formation, starters)


def build_svg(lineup: dict) -> str:
    formation = html.escape(lineup.get("formation", "4-3-3"))
    opponent = html.escape(lineup.get("opponent", "TBD"))
    starters = lineup.get("starting_xi") or []
    width, height = 720, 520
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#1f7a3a"/>',
        '<rect x="40" y="40" width="640" height="440" fill="none" stroke="#ffffff" stroke-width="3"/>',
        '<line x1="40" y1="260" x2="680" y2="260" stroke="#ffffff" stroke-width="2"/>',
        '<circle cx="360" cy="260" r="60" fill="none" stroke="#ffffff" stroke-width="2"/>',
        f'<text x="360" y="28" text-anchor="middle" fill="#ffffff" font-size="20" font-family="Arial">'
        f'ScoutMatch FC — {formation} vs {opponent}</text>',
        '<text x="360" y="52" text-anchor="middle" fill="#ffe08a" font-size="12" font-family="Arial">'
        "PROPOSED LINEUP — PENDING HEAD COACH REVIEW</text>",
    ]
    for player, x_ratio, y_ratio in _slot_positions(lineup.get("formation", "4-3-3"), starters):
        cx = 40 + int(640 * x_ratio)
        cy = 40 + int(440 * y_ratio)
        status = player.get("status", "AVAILABLE")
        fill = "#f4c542" if status == "PENDING_MANAGEMENT_APPROVAL" else "#ffffff"
        name = html.escape(_short_name(player.get("name", "")))
        pos = html.escape(player.get("position", ""))
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="22" fill="{fill}" stroke="#0d3d1f" stroke-width="2"/>')
        parts.append(
            f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" fill="#0d3d1f" font-size="12" font-family="Arial">'
            f'{name}</text>'
        )
        parts.append(
            f'<text x="{cx}" y="{cy + 38}" text-anchor="middle" fill="#ffffff" font-size="10" font-family="Arial">'
            f'{pos}</text>'
        )
        if status == "PENDING_MANAGEMENT_APPROVAL":
            parts.append(
                f'<text x="{cx}" y="{cy - 30}" text-anchor="middle" fill="#ffe08a" font-size="9" font-family="Arial">'
                f'PENDING APPROVAL</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _object_key(lineup_id: str, stamp: str) -> str:
    return f"{LINEUP_PREFIX.rstrip('/')}/{slug_name(lineup_id)}/{stamp.replace(':', '').replace('+00:00', 'Z')}.svg"


def _use_local() -> bool:
    return (
        os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}
        or not BUCKET.strip()
    )


def _selection_remaining_budget(selection: dict, *, base_remaining: int) -> int | None:
    if selection.get("remaining_budget_eur") is not None:
        return int(selection["remaining_budget_eur"])
    reserved = selection.get("reserved_amount_eur")
    if reserved is not None:
        return max(base_remaining - int(reserved), 0)
    return None


def _selection_matches_lineup_context(selection: dict, ctx_id: str) -> bool:
    if selection.get("demo_season_id") and selection.get("demo_season_id") != active_demo_season_id():
        return False
    selection_ctx = str(selection.get("planning_context_id") or "").strip()
    if ctx_id and selection_ctx and selection_ctx != ctx_id:
        return False
    return selection.get("reservation_status") == "RESERVED_PENDING_APPROVAL"


def _remaining_budget_for_lineup(lineup: dict) -> int:
    ctx_id = str(lineup.get("planning_context_id") or "").strip()
    remaining, _ = available_budget_from_context(planning_context_id=ctx_id or None)
    base_remaining = int(remaining or 0)
    for starter in lineup.get("starting_xi") or []:
        if starter.get("status") != "PENDING_MANAGEMENT_APPROVAL":
            continue
        name_key = normalize_name(starter.get("name", ""))
        selection = get_item(f"player_selection#{name_key}")
        critical = get_item(f"critical_decision#{name_key}")
        pending_record = None
        if selection and _selection_matches_lineup_context(selection, ctx_id):
            pending_record = selection
        elif critical and critical.get("status") == "PENDING_MANAGEMENT_APPROVAL":
            same_scope = (
                critical.get("demo_season_id") == active_demo_season_id()
                or critical.get("demo_scope") == active_demo_season_id()
            )
            if same_scope:
                pending_record = critical
        if not pending_record:
            continue
        if pending_record is critical:
            if pending_record.get("remaining_budget_eur") is not None:
                return int(pending_record["remaining_budget_eur"])
            reserved = pending_record.get("reserved_amount_eur") or pending_record.get("salary_eur")
            if reserved is not None:
                return max(base_remaining - int(reserved), 0)
            continue
        scoped = _selection_remaining_budget(pending_record, base_remaining=base_remaining)
        if scoped is not None:
            return scoped
    for selection in list_by_prefix("player_selection#"):
        if not _selection_matches_lineup_context(selection, ctx_id):
            continue
        scoped = _selection_remaining_budget(selection, base_remaining=base_remaining)
        if scoped is not None:
            return scoped
    for critical in list_by_prefix("critical_decision#"):
        if critical.get("status") != "PENDING_MANAGEMENT_APPROVAL":
            continue
        if critical.get("demo_season_id") and critical.get("demo_season_id") != active_demo_season_id():
            continue
        if critical.get("remaining_budget_eur") is not None:
            return int(critical["remaining_budget_eur"])
        reserved = critical.get("reserved_amount_eur") or critical.get("salary_eur")
        if reserved is not None:
            return max(base_remaining - int(reserved), 0)
    return base_remaining


def generate_board(lineup_id: str = "") -> tuple[dict | None, str]:
    lineup = get_current_lineup()
    if not lineup:
        return None, "No proposed lineup has been saved for head-coach review yet."

    svg = build_svg(lineup)
    stamp = _now()
    resolved_id = lineup_id or lineup.get("lineup_id", "current")
    key = _object_key(resolved_id, stamp)
    if _use_local():
        _LOCAL_SVG[resolved_id] = svg
    else:
        import boto3

        boto3.client("s3").put_object(
            Bucket=BUCKET,
            Key=key,
            Body=svg.encode("utf-8"),
            ContentType="image/svg+xml",
        )
    put_item(
        entity_key=f"lineup_board#{resolved_id}",
        item_type="LINEUP_BOARD_METADATA",
        payload={
            "lineup_id": resolved_id,
            "object_key": key,
            "generated_at": stamp,
            "formation": lineup.get("formation"),
            "opponent": lineup.get("opponent"),
        },
    )
    remaining = _remaining_budget_for_lineup(lineup)
    return {
        "status": "LINEUP_BOARD_GENERATED",
        "lineup_id": resolved_id,
        "formation": lineup.get("formation"),
        "opponent": lineup.get("opponent"),
        "generated_at": stamp,
        "object_key": key,
        "image_route": f"/api/recruitment-advisor/lineups/{resolved_id}/image",
        "remaining_budget_eur": remaining,
        "player_count": len(lineup.get("starting_xi") or []),
    }, ""


def get_local_svg(lineup_id: str) -> str | None:
    return _LOCAL_SVG.get(lineup_id)
