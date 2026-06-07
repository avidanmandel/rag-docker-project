"""GenerateVisualSquadAndLineupBoard workflow."""

from __future__ import annotations

from lineup_svg import generate_board
from lineup_store import finalize_lineup, get_current_lineup
from operations_store import get_item, list_by_prefix
from validation import normalize_name


def prepare_save_lineup(params: dict) -> dict:
    formation = (params.get("formation") or "4-3-3").strip()
    demo = str(params.get("demo_lineup") or "").lower() in {"1", "true", "yes", "demo"}
    return {
        "status": "PENDING_CONFIRMATION",
        "confirmation_required": True,
        "mission_mode": "SAVE_AND_RENDER",
        "formation": formation,
        "demo_lineup": demo,
        "players": 11 if demo else "validated on confirm",
        "message": f"Confirm saving the proposed {formation} lineup for head-coach review.",
        "user_boundary": "The lineup is not approved until the head coach reviews it.",
    }


def deny_save_lineup() -> dict:
    return {
        "status": "CANCELLED",
        "message": "The lineup save was cancelled. No lineup record was created.",
    }


def save_and_render_lineup(params: dict) -> tuple[dict | None, str]:
    record, err = finalize_lineup(params)
    if err:
        return None, err
    body, gen_err = generate_board("")
    if gen_err:
        return record, gen_err
    merged = {**(record or {}), **(body or {})}
    merged["status"] = "PENDING_HEAD_COACH_REVIEW"
    merged["mission_mode"] = "SAVE_AND_RENDER"
    merged["squad_board_type"] = "visual_squad_board"
    merged.update(_board_context())
    return merged, ""


def render_current_board() -> tuple[dict | None, str]:
    lineup = get_current_lineup()
    if not lineup:
        return {
            "status": "NOT_FOUND",
            "message": "No proposed lineup has been saved for head-coach review yet.",
        }, ""
    body, err = generate_board("")
    if err:
        return None, err
    body = body or {}
    body["status"] = "LINEUP_BOARD_GENERATED"
    body["mission_mode"] = "RENDER_CURRENT"
    body["squad_board_type"] = "visual_squad_board"
    body.update(_board_context())
    return body, ""


def _board_context() -> dict:
    transfer_out = list_by_prefix("transfer_out_review#")
    pending_transfer_out = [
        r.get("player_name")
        for r in transfer_out
        if r.get("status") == "PENDING_TECHNICAL_DIRECTOR_REVIEW"
    ]
    selections = list_by_prefix("critical_decision#") or list_by_prefix("player_selection#")
    pending_candidates = [
        r.get("candidate_name") or r.get("selected_player")
        for r in selections
        if r.get("status") == "PENDING_MANAGEMENT_APPROVAL"
        or r.get("approval_status") == "PENDING_MANAGEMENT_APPROVAL"
    ]
    remaining = None
    for r in selections:
        if r.get("remaining_budget_eur") is not None:
            remaining = int(r["remaining_budget_eur"])
            break
    return {
        "pending_management_candidates": pending_candidates,
        "pending_transfer_out_players": pending_transfer_out,
        "remaining_confirmed_budget_eur": remaining,
        "opening_fixture": "Barcelona",
        "transfer_window": "Open",
        "player_markers": _marker_statuses(pending_candidates, pending_transfer_out),
    }


def _marker_statuses(candidates: list, transfer_out: list) -> list[dict]:
    markers = []
    for name in candidates:
        if name:
            markers.append({"player_name": name, "marker_status": "Pending management approval"})
    for name in transfer_out:
        if name:
            markers.append({"player_name": name, "marker_status": "Transfer-out review pending"})
    return markers
