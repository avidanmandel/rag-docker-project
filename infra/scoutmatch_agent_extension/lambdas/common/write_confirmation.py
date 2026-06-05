"""Write-action confirmation helpers for Bedrock Action Groups."""

from __future__ import annotations

import os
from typing import Any

from bedrock_response import build_function_response


WRITE_ACTIONS = frozenset(
    {
        "AddCandidateToShortlist",
        "UpdateCandidateShortlistStatus",
        "RemoveCandidateFromShortlist",
        "CreateRecruitmentBrief",
        "StartCandidateReviewWorkflow",
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
        "RecordPlayerAvailabilityChange",
    }
)


def _confirmation_state(event: dict[str, Any]) -> str:
    for key in ("confirmationState", "confirmation_state"):
        raw = str(event.get(key, "")).strip().upper()
        if raw:
            return raw
    inv = event.get("actionGroupInvocationInput") or {}
    if isinstance(inv, dict):
        raw = str(inv.get("confirmationState", "")).strip().upper()
        if raw:
            return raw
    return ""


def is_write_denied(event: dict[str, Any]) -> bool:
    return _confirmation_state(event) in {"DENY", "DENIED", "REJECT", "REJECTED"}


def is_write_confirmed(event: dict[str, Any]) -> bool:
    if is_write_denied(event):
        return False
    state = _confirmation_state(event)
    if state in {"CONFIRM", "CONFIRMED", "ACCEPT", "ACCEPTED"}:
        return True
    attrs = event.get("sessionAttributes") or {}
    if isinstance(attrs, dict):
        if str(attrs.get("workflow_internal", "")).lower() == "true":
            return True
        if str(attrs.get("write_confirmed", "")).strip().lower() in {
            "true",
            "1",
            "yes",
            "confirmed",
        }:
            return True
    if (
        os.getenv("SCOUTMATCH_BEDROCK_NATIVE_CONFIRMATION", "").lower() in {"1", "true", "yes"}
        and (event.get("function") or "") in WRITE_ACTIONS
        and event.get("invocationId")
    ):
        return True
    return False


def pending_confirmation_response(
    *,
    action_group: str,
    function_name: str,
    message: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    return build_function_response(
        action_group=action_group,
        function_name=function_name,
        body={
            "status": "PENDING_CONFIRMATION",
            "message": message,
            "confirmation_required": True,
        },
        event=event,
    )
