"""Runtime feature flags for ScoutMatch business workflow v2."""

from __future__ import annotations

import os


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def business_workflow_v2_enabled() -> bool:
    return _truthy("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED")


def email_mode() -> str:
    return (os.getenv("SCOUTMATCH_EMAIL_MODE") or "disabled").strip().lower()


def calendar_mode() -> str:
    return (os.getenv("SCOUTMATCH_CALENDAR_MODE") or "ics_fallback").strip().lower()


def scouting_reminder_mode() -> str:
    return (os.getenv("SCOUTMATCH_SCOUTING_REMINDER_MODE") or "disabled").strip().lower()


def demo_replay_enabled() -> bool:
    return _truthy("SCOUTMATCH_DEMO_REPLAY_ENABLED", "true")
