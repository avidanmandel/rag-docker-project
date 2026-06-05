"""SVG lineup board generation."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from budget_ledger import available_budget_from_context
from lineup_store import get_current_lineup
from validation import assign_formation_slots, slug_name

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
    formation = lineup.get("formation", "4-3-3")
    opponent = lineup.get("opponent", "TBD")
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
    ]
    for player, x_ratio, y_ratio in _slot_positions(formation, starters):
        cx = 40 + int(640 * x_ratio)
        cy = 40 + int(440 * y_ratio)
        status = player.get("status", "AVAILABLE")
        fill = "#f4c542" if status == "PENDING_MANAGEMENT_APPROVAL" else "#ffffff"
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="22" fill="{fill}" stroke="#0d3d1f" stroke-width="2"/>')
        parts.append(
            f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" fill="#0d3d1f" font-size="12" font-family="Arial">'
            f'{_short_name(player.get("name", ""))}</text>'
        )
        parts.append(
            f'<text x="{cx}" y="{cy + 38}" text-anchor="middle" fill="#ffffff" font-size="10" font-family="Arial">'
            f'{player.get("position", "")}</text>'
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


def generate_board() -> tuple[dict | None, str]:
    lineup = get_current_lineup()
    if not lineup:
        return None, "No finalized lineup found. Finalize the current lineup first."

    svg = build_svg(lineup)
    stamp = _now()
    lineup_id = lineup.get("lineup_id", "current")
    key = _object_key(lineup_id, stamp)
    if _use_local():
        _LOCAL_SVG[lineup_id] = svg
    else:
        import boto3

        boto3.client("s3").put_object(
            Bucket=BUCKET,
            Key=key,
            Body=svg.encode("utf-8"),
            ContentType="image/svg+xml",
        )
    remaining, _ = available_budget_from_context()
    return {
        "status": "RENDERED",
        "lineup_id": lineup_id,
        "formation": lineup.get("formation"),
        "opponent": lineup.get("opponent"),
        "generated_at": stamp,
        "object_key": key,
        "image_route": f"/api/recruitment-advisor/lineups/{lineup_id}/image",
        "remaining_budget_eur": remaining,
        "player_count": len(lineup.get("starting_xi") or []),
    }, ""


def get_local_svg(lineup_id: str) -> str | None:
    return _LOCAL_SVG.get(lineup_id)
