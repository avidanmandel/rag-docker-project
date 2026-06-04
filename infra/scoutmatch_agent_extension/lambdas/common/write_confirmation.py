"""Write-action confirmation helpers for Bedrock Action Groups."""

from __future__ import annotations

from typing import Any

from bedrock_response import build_function_response


WRITE_ACTIONS = frozenset(
    {
        "AddCandidateToShortlist",
        "UpdateCandidateShortlistStatus",
        "RemoveCandidateFromShortlist",
        "CreateRecruitmentBrief",
        "StartCandidateReviewWorkflow",
    }
)


def is_write_confirmed(event: dict[str, Any]) -> bool:
    attrs = event.get("sessionAttributes") or {}
    if not isinstance(attrs, dict):
        return False
    return str(attrs.get("write_confirmed", "")).strip().lower() in {
        "true",
        "1",
        "yes",
        "confirmed",
    }


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
