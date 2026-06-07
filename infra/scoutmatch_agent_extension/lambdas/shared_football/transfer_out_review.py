"""OpenTransferOutReviewCase workflow."""

from __future__ import annotations

import hashlib
import uuid

from operations_store import active_demo_season_id, get_item, put_item
from season_context import TRANSFER_OUT_PROFILES
from validation import normalize_name, resolve_squad_player, resolve_transfer_candidate


def explain_transfer_out_candidate(player_name: str) -> dict:
    profile = TRANSFER_OUT_PROFILES.get(normalize_name(player_name))
    if not profile:
        squad = resolve_squad_player(player_name)
        if not squad:
            return {
                "status": "NOT_FOUND",
                "message": f"'{player_name}' is not in the current 15-player squad.",
            }
        return {
            "status": "ADVISORY",
            "player_name": squad["display_name"],
            "message": "No approved transfer-out review profile is available for this player.",
        }
    return {
        "status": "ADVISORY",
        "player_name": profile["display_name"],
        "reason": profile["review_reason"],
        "estimated_budget_release_eur": profile["estimated_budget_release_eur"],
        "expected_minutes": profile["expected_minutes"],
        "tactical_fit_summary": profile["tactical_fit_summary"],
        "squad_overlap_summary": profile["squad_overlap_summary"],
        "hypothetical_note": (
            "Estimated released budget is hypothetical until the technical director approves the sale."
        ),
        "prompt": "Would you like me to open a transfer-out review case?",
    }


def prepare_transfer_out_case(player_name: str, *, review_reason: str = "") -> dict:
    if resolve_transfer_candidate(player_name):
        return {
            "status": "FAILURE",
            "message": "Transfer-out review applies to current squad players only, not recruitment candidates.",
        }
    profile = TRANSFER_OUT_PROFILES.get(normalize_name(player_name))
    if not profile:
        squad = resolve_squad_player(player_name)
        if not squad:
            return {
                "status": "FAILURE",
                "message": f"'{player_name}' is not in the current 15-player squad.",
            }
        return {"status": "FAILURE", "message": "No approved transfer-out review profile is available."}
    reason = review_reason.strip() or profile["review_reason"]
    return {
        "status": "PENDING_CONFIRMATION",
        "confirmation_required": True,
        "player_name": profile["display_name"],
        "player_position": profile["position"],
        "current_salary_eur": profile["salary_eur"],
        "estimated_budget_release_eur": profile["estimated_budget_release_eur"],
        "review_reason": reason,
        "expected_minutes": profile["expected_minutes"],
        "message": f"Confirm opening a transfer-out review case for {profile['display_name']}.",
        "user_boundary": "The player has not been sold. A technical-director review is still required.",
    }


def deny_transfer_out_case() -> dict:
    return {
        "status": "CANCELLED",
        "message": (
            "The transfer-out review was cancelled. No review case was created. "
            "No budget value was changed."
        ),
    }


def open_transfer_out_case(player_name: str, *, review_reason: str = "") -> tuple[dict | None, str]:
    prep = prepare_transfer_out_case(player_name, review_reason=review_reason)
    if prep.get("status") != "PENDING_CONFIRMATION":
        return prep if prep.get("status") == "FAILURE" else None, prep.get("message", "Unable to open case.")
    profile = TRANSFER_OUT_PROFILES[normalize_name(player_name)]
    idem = hashlib.sha256(f"transfer-out:{profile['display_name']}".encode()).hexdigest()[:16]
    entity_key = f"transfer_out_review#{normalize_name(profile['display_name'])}"
    existing = get_item(entity_key)
    if existing and existing.get("idempotency_key") == idem:
        return {
            "status": "PENDING_TECHNICAL_DIRECTOR_REVIEW",
            "review_case_id": existing.get("review_case_id"),
            "player_name": profile["display_name"],
            "reason": existing.get("review_reason"),
            "estimated_budget_release_eur": existing.get("estimated_budget_release_eur"),
            "idempotent": True,
            "user_boundary": "The player has not been sold. A technical-director review is still required.",
        }, ""
    record = {
        "review_case_id": str(uuid.uuid4()),
        "player_name": profile["display_name"],
        "player_position": profile["position"],
        "current_salary_eur": profile["salary_eur"],
        "estimated_budget_release_eur": profile["estimated_budget_release_eur"],
        "review_reason": review_reason.strip() or profile["review_reason"],
        "expected_minutes": profile["expected_minutes"],
        "squad_overlap_summary": profile["squad_overlap_summary"],
        "tactical_fit_summary": profile["tactical_fit_summary"],
        "status": "PENDING_TECHNICAL_DIRECTOR_REVIEW",
        "demo_scope": active_demo_season_id(),
        "idempotency_key": idem,
    }
    put_item(entity_key=entity_key, item_type="TRANSFER_OUT_REVIEW", payload=record)
    return {
        "status": "PENDING_TECHNICAL_DIRECTOR_REVIEW",
        "review_case_id": record["review_case_id"],
        "player_name": profile["display_name"],
        "reason": record["review_reason"],
        "estimated_budget_release_eur": record["estimated_budget_release_eur"],
        "idempotent": False,
        "user_boundary": "The player has not been sold. A technical-director review is still required.",
    }, ""
