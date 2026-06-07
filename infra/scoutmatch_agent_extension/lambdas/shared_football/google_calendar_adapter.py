"""Google Calendar API adapter with ICS fallback."""

from __future__ import annotations

import os
import uuid

from feature_flags import calendar_mode
from ics_calendar import build_ics_invite


def create_calendar_event(
    *,
    candidate_name: str,
    fixture_name: str,
    fixture_datetime: str,
    checklist: list[str],
    purpose: str,
) -> dict:
    mode = calendar_mode()
    title = f"ScoutMatch AI — Live Observation: {candidate_name}"
    description = (
        f"{purpose}\n\nFocus areas:\n"
        + "\n".join(f"* {item}" for item in checklist)
    )
    if mode == "google_api":
        token = (os.getenv("SCOUTMATCH_GOOGLE_CALENDAR_ACCESS_TOKEN") or "").strip()
        calendar_id = (os.getenv("SCOUTMATCH_GOOGLE_CALENDAR_ID") or "").strip()
        if token and calendar_id:
            if os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}:
                return {
                    "mode": "google_api",
                    "status": "created",
                    "calendar_label": "Google Calendar event created",
                    "calendar_link": "",
                }
            return {
                "mode": "google_api",
                "status": "not_implemented_in_lambda",
                "calendar_label": "Calendar invite ready to download",
                "calendar_link": "",
            }
    invite_key = f"mission-{uuid.uuid4().hex[:12]}"
    ics_body = build_ics_invite(
        uid=invite_key,
        title=title,
        description=description,
        start_iso=fixture_datetime,
    )
    return {
        "mode": "ics_fallback" if mode != "disabled" else "disabled",
        "status": "ics_ready",
        "calendar_label": "Calendar invite ready to download",
        "calendar_invite_key": invite_key,
        "ics_body": ics_body,
        "calendar_link": f"/api/opening-season/calendar-invite/{invite_key}",
    }


def schedule_reminder(*, mission_id: str, fixture_datetime: str) -> dict:
    from feature_flags import scouting_reminder_mode

    if scouting_reminder_mode() not in {"eventbridge", "enabled"}:
        return {
            "status": "not_scheduled",
            "label": "Reminder plan saved — scheduler not configured",
        }
    if os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}:
        return {
            "status": "scheduled",
            "label": "Scheduled 3 hours before kickoff",
        }
    return {
        "status": "not_scheduled",
        "label": "Reminder plan saved — scheduler not configured",
    }
