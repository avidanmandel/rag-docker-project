"""CreateAndReviewScoutingMission workflow."""

from __future__ import annotations

import hashlib
import uuid

from google_calendar_adapter import create_calendar_event, schedule_reminder
from operations_store import active_demo_season_id, get_item, put_item
from season_context import OBSERVATION_CHECKLIST_RB, UPCOMING_FIXTURES, load_completed_observation_report
from validation import normalize_name, resolve_transfer_candidate, slug_name


def prepare_scouting_mission(
    *,
    candidate_name: str,
    purpose: str = "Final live observation before management review",
) -> dict:
    candidate = resolve_transfer_candidate(candidate_name)
    if not candidate:
        return {
            "status": "FAILURE",
            "message": f"Candidate '{candidate_name}' is not grounded in approved ScoutMatch records.",
        }
    fixture = UPCOMING_FIXTURES.get(normalize_name(candidate_name), UPCOMING_FIXTURES["ron ben ari"])
    return {
        "status": "PENDING_CONFIRMATION",
        "confirmation_required": True,
        "mission_mode": "CREATE_MISSION",
        "candidate_name": candidate["display_name"],
        "purpose": purpose,
        "fixture_name": fixture["fixture_name"],
        "fixture_datetime": fixture["fixture_datetime"],
        "display_date": fixture["display_date"],
        "observation_checklist": OBSERVATION_CHECKLIST_RB,
        "message": f"Confirm creating a scouting mission for {candidate['display_name']}.",
    }


def deny_scouting_mission() -> dict:
    return {
        "status": "CANCELLED",
        "message": "The scouting mission was cancelled. No mission record was created.",
    }


def create_scouting_mission(
    *,
    candidate_name: str,
    purpose: str = "Final live observation before management review",
) -> tuple[dict | None, str]:
    prep = prepare_scouting_mission(candidate_name=candidate_name, purpose=purpose)
    if prep.get("status") != "PENDING_CONFIRMATION":
        return prep, prep.get("message", "Unable to create mission.")
    candidate = resolve_transfer_candidate(candidate_name)
    assert candidate
    idem = hashlib.sha256(f"mission:{candidate['display_name']}".encode()).hexdigest()[:16]
    entity_key = f"scouting_mission#{normalize_name(candidate['display_name'])}"
    existing = get_item(entity_key)
    if existing and existing.get("idempotency_key") == idem:
        return _mission_card(existing, idempotent=True), ""
    fixture = UPCOMING_FIXTURES.get(normalize_name(candidate_name), UPCOMING_FIXTURES["ron ben ari"])
    calendar = create_calendar_event(
        candidate_name=candidate["display_name"],
        fixture_name=fixture["fixture_name"],
        fixture_datetime=fixture["fixture_datetime"],
        checklist=OBSERVATION_CHECKLIST_RB,
        purpose=purpose,
    )
    reminder = schedule_reminder(
        mission_id=entity_key,
        fixture_datetime=fixture["fixture_datetime"],
    )
    record = {
        "mission_id": str(uuid.uuid4()),
        "mission_mode": "CREATE_MISSION",
        "candidate_name": candidate["display_name"],
        "fixture_name": fixture["fixture_name"],
        "fixture_datetime": fixture["fixture_datetime"],
        "display_date": fixture["display_date"],
        "purpose": purpose,
        "observation_checklist": OBSERVATION_CHECKLIST_RB,
        "calendar_mode": calendar.get("mode"),
        "calendar_event_status": calendar.get("status"),
        "calendar_event_reference": calendar.get("calendar_link", ""),
        "calendar_invite_key": calendar.get("calendar_invite_key", ""),
        "ics_body": calendar.get("ics_body", ""),
        "reminder_status": reminder.get("status"),
        "reminder_label": reminder.get("label"),
        "status": "PENDING_SCOUT_OBSERVATION",
        "demo_scope": active_demo_season_id(),
        "idempotency_key": idem,
    }
    put_item(entity_key=entity_key, item_type="SCOUTING_MISSION", payload=record)
    return _mission_card(record, idempotent=False), ""


def _mission_card(record: dict, *, idempotent: bool) -> dict:
    calendar_label = record.get("calendar_label") or (
        "Google Calendar event created"
        if record.get("calendar_mode") == "google_api" and record.get("calendar_event_status") == "created"
        else "Calendar invite ready to download"
    )
    return {
        "status": "PENDING_SCOUT_OBSERVATION",
        "mission_id": record.get("mission_id"),
        "candidate_name": record.get("candidate_name"),
        "purpose": record.get("purpose"),
        "fixture_name": record.get("fixture_name"),
        "display_date": record.get("display_date"),
        "observation_checklist": record.get("observation_checklist"),
        "calendar_label": calendar_label,
        "calendar_link": record.get("calendar_event_reference") or record.get("calendar_link"),
        "calendar_invite_key": record.get("calendar_invite_key"),
        "reminder_label": record.get("reminder_label", "Reminder plan saved"),
        "mission_card_type": "scouting_mission",
        "idempotent": idempotent,
    }


def review_completed_mission(candidate_name: str) -> dict:
    slug = slug_name(candidate_name)
    report = load_completed_observation_report(slug)
    if not report:
        return {
            "status": "NOT_FOUND",
            "message": f"No completed demo scouting report is available for {candidate_name}.",
        }
    return {
        "status": "READY_FOR_RECRUITMENT_REVIEW",
        "report_label": "Demo replay: completed scouting observation",
        "report_type": report.get("report_type", "synthetic_demo_replay"),
        "candidate_name": report.get("candidate_name"),
        "match": report.get("match"),
        "observed_performance": {
            "defensive_recoveries": report.get("defensive_recoveries"),
            "overlapping_runs": report.get("overlapping_runs"),
            "key_passes": report.get("key_passes"),
            "pressing_intensity": report.get("pressing_intensity"),
            "recovery_speed": report.get("recovery_speed"),
            "defensive_positioning": report.get("defensive_positioning"),
        },
        "main_risk": report.get("main_risk"),
        "recommendation": report.get("recommendation"),
        "ai_summary": (
            f"{report.get('candidate_name')} remains a strong fit for the documented right-back gap."
        ),
        "report_route": f"/api/opening-season/completed-observations/{slug}",
        "completed_report_key": slug,
    }
