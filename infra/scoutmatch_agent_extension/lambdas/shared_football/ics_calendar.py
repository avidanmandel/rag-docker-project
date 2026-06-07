"""Safe ICS calendar invite generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def build_ics_invite(
    *,
    uid: str,
    title: str,
    description: str,
    start_iso: str,
    duration_hours: int = 2,
) -> str:
    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(hours=duration_hours)
    fmt = "%Y%m%dT%H%M%SZ"

    def _fmt(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime(fmt)

    desc = description.replace("\n", "\\n")
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//ScoutMatch AI//Scouting Mission//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}@scoutmatch.ai\r\n"
        f"DTSTAMP:{_fmt(datetime.now(timezone.utc))}\r\n"
        f"DTSTART:{_fmt(start)}\r\n"
        f"DTEND:{_fmt(end)}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DESCRIPTION:{desc}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
