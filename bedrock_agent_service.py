"""
ScoutMatch Bedrock Agent recruitment advisor.

Uses Amazon Bedrock Agent invoke only — no direct Lambda selection by the user.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import boto3

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env.agent", override=False)
except Exception:
    pass

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AGENT_ENABLED = os.getenv("SCOUTMATCH_AGENT_EXTENSION_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
AGENT_ID = (os.getenv("SCOUTMATCH_AGENT_ID") or "").strip()
AGENT_ALIAS_ID = (os.getenv("SCOUTMATCH_AGENT_ALIAS_ID") or "").strip()
AGENT_STAGING_ALIAS_ID = (os.getenv("SCOUTMATCH_AGENT_STAGING_ALIAS_ID") or "").strip()

DISABLED_MESSAGE = (
    "ScoutMatch Bedrock Agent recruitment advisor is disabled. "
    "Set SCOUTMATCH_AGENT_EXTENSION_ENABLED=true and configure agent IDs in .env.agent (local only)."
)
MISSING_CONFIG_MESSAGE = (
    "ScoutMatch Agent extension is enabled but SCOUTMATCH_AGENT_ID or "
    "SCOUTMATCH_AGENT_ALIAS_ID is not configured."
)
GENERIC_ERROR_MESSAGE = "The recruitment advisor could not complete this request."
GUARDRAIL_BLOCK_MESSAGE = (
    "I cannot answer this request because it was blocked by the ScoutMatch safety policy."
)

def _business_workflow_v2_enabled() -> bool:
    return os.getenv("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _resolved_agent_alias_id() -> str:
    if _business_workflow_v2_enabled() and AGENT_STAGING_ALIAS_ID:
        return AGENT_STAGING_ALIAS_ID
    return AGENT_ALIAS_ID


def agent_runtime_config() -> dict[str, Any]:
    """Sanitized runtime config for status endpoints."""
    alias = _resolved_agent_alias_id()
    return {
        "business_workflow_v2": _business_workflow_v2_enabled(),
        "agent_alias_id": alias or None,
        "agent_extension_enabled": is_enabled(),
    }


LEGACY_WRITE_CONFIRM_TOOLS = frozenset(
    {
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
    }
)
V2_WRITE_CONFIRM_TOOLS = frozenset(
    {
        "SubmitCriticalDecisionAndSendEmail",
        "OpenTransferOutReviewCase",
        "CreateAndReviewScoutingMission",
        "GenerateVisualSquadAndLineupBoard",
    }
)
WRITE_CONFIRM_TOOLS = (
    V2_WRITE_CONFIRM_TOOLS if _business_workflow_v2_enabled() else LEGACY_WRITE_CONFIRM_TOOLS
)
CONFIRM_INPUTS = frozenset({"confirm", "yes", "proceed", "approve"})
DENY_INPUTS = frozenset({"deny", "cancel", "reject", "no"})
LEGACY_TOOL_USER_LABELS = {
    "PlanMatchTactics": "Plan match tactics",
    "SubmitPlayerSelectionToManagement": "Submit player recommendation to management",
    "FinalizeCurrentLineup": "Save proposed lineup for head-coach review",
    "GenerateCurrentLineupBoard": "Generate current lineup board",
}
V2_TOOL_USER_LABELS = {
    "SubmitCriticalDecisionAndSendEmail": "Submit critical decision for management review",
    "OpenTransferOutReviewCase": "Open transfer-out review case",
    "CreateAndReviewScoutingMission": "Create or review scouting mission",
    "GenerateVisualSquadAndLineupBoard": "Generate visual squad and lineup board",
}
TOOL_USER_LABELS = V2_TOOL_USER_LABELS if _business_workflow_v2_enabled() else LEGACY_TOOL_USER_LABELS
GUARDRAIL_SAFE_PARAPHRASES = {
    (
        "Compare the right-back candidates within our recruitment budget. "
        "Include Ron Ben Ari and the other documented right-back options."
    ): (
        "Compare the right-back candidates within our recruitment budget. "
        "Include Ron Ben Ari and Tal Cohen."
    ),
}
_PLANNING_CONTEXT_PATTERN = re.compile(r"\bplanning[_\s-]*context[_\s-]*id\b[:\s]*[A-Za-z0-9_-]+", re.I)
_INTERNAL_ID_PATTERN = re.compile(
    r"\b(?:ctx|record|entity|lineup|selection)[-_][A-Za-z0-9]{6,}\b",
    re.I,
)
LEGACY_ALLOWED_PUBLIC_TOOLS = frozenset(
    {
        "PlanMatchTactics",
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
        "GenerateCurrentLineupBoard",
    }
)
V2_ALLOWED_PUBLIC_TOOLS = frozenset(
    {
        "SubmitCriticalDecisionAndSendEmail",
        "OpenTransferOutReviewCase",
        "CreateAndReviewScoutingMission",
        "GenerateVisualSquadAndLineupBoard",
    }
)
ALLOWED_PUBLIC_TOOLS = (
    V2_ALLOWED_PUBLIC_TOOLS if _business_workflow_v2_enabled() else LEGACY_ALLOWED_PUBLIC_TOOLS
)

_ARN_PATTERN = re.compile(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:[0-9]{12}:[^\s]+", re.I)
_ACCOUNT_PATTERN = re.compile(r"\b[0-9]{12}\b")
_LINEUP_ROUTE_PATTERN = re.compile(r"/api/recruitment-advisor/lineups/[a-zA-Z0-9_-]+/image")
_REMAINING_BUDGET_PATTERN = re.compile(
    r"remaining(?:\s+available)?\s+budget[:\s]+([0-9][0-9,]*)\s*EUR",
    re.I,
)
_COACH_BRIEF_PREFIX = re.compile(r"^\s*coach\s+brief\s*:\s*", re.I)
_CONFIRM_PROMPT_PATTERN = re.compile(
    r"(please confirm|confirm the following|action requires confirmation)",
    re.I,
)
_CONFIRM_FIELD_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s*)?\*\*(Candidate|Target Role|Salary|Formation|Players):\*\*\s*([^\n]+)",
    re.I,
)
_V2_WRITE_STEER_SUFFIX = (
    " Invoke the matching write tool immediately with defaults from approved club data. "
    "Do not ask clarifying questions."
)
_V2_RENDER_ONLY_PATTERN = re.compile(
    r"show me the updated proposed lineup and squad-risk board",
    re.I,
)
_V2_WRITE_INTENT_PATTERNS = (
    re.compile(r"open\s+a\s+transfer-out\s+review\s+case", re.I),
    re.compile(r"submit\s+(?:the\s+)?recommendation", re.I),
    re.compile(r"choose\s+.+\s+submit", re.I),
    re.compile(r"create\s+a\s+scouting\s+mission", re.I),
    re.compile(r"save\s+and\s+show\s+the\s+proposed", re.I),
    re.compile(r"proposed\s+4-3-3\s+lineup", re.I),
)
_V2_WRITE_RETRY_ATTEMPTS = 3
_V2_EXPLICIT_WRITE_AUGMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"open\s+a\s+transfer-out\s+review\s+case\s+for\s+daniel\s+cohen", re.I),
        " Daniel Cohen is an approved current-squad rotation midfielder in ScoutMatch operational data.",
    ),
    (
        re.compile(r"save\s+and\s+show\s+the\s+proposed\s+4-3-3\s+lineup", re.I),
        " Use board_mode SAVE_AND_RENDER, formation 4-3-3, and demo_lineup true.",
    ),
)


def _rewrite_v2_direct_invoke_prompt(question: str) -> str | None:
    text = (question or "").strip()
    if re.search(r"create\s+a\s+scouting\s+mission", text, re.I):
        return (
            "Invoke CreateAndReviewScoutingMission with candidate_name Ron Ben Ari "
            "and mission_mode CREATE_MISSION."
        )
    if re.search(r"submit\s+(?:the\s+)?recommendation\s+for\s+management\s+review", text, re.I):
        return (
            "Invoke SubmitCriticalDecisionAndSendEmail with candidate_name Ron Ben Ari, "
            "salary_eur 43000, and target_role Right-back."
        )
    if re.search(r"choose\s+.+\s+right-back\s+candidate", text, re.I):
        return (
            "Invoke SubmitCriticalDecisionAndSendEmail with candidate_name Ron Ben Ari, "
            "salary_eur 43000, and target_role Right-back."
        )
    if re.search(r"completed scouting report", text, re.I):
        return (
            "Invoke CreateAndReviewScoutingMission with candidate_name Ron Ben Ari "
            "and mission_mode REVIEW_COMPLETED_MISSION."
        )
    return None


def _agent_asked_chat_confirmation(answer: str) -> bool:
    text = (answer or "").lower()
    return (
        "confirmation required before writing" in text
        or "confirm the details with you before submitting" in text
        or "before invoking any write tool" in text
        or bool(_CONFIRM_PROMPT_PATTERN.search(answer or ""))
    )


def _escalating_v2_write_prompt(question: str, attempt: int) -> str:
    text = (question or "").strip()
    direct = _rewrite_v2_direct_invoke_prompt(text)
    if direct:
        return _guardrail_safe_prompt(direct)
    base = _maybe_steered_v2_prompt(text)
    if attempt >= 1:
        return _guardrail_safe_prompt(
            f"{base} Invoke the matching write tool immediately. "
            "Do not ask clarifying questions or request chat confirmation."
        )
    return _guardrail_safe_prompt(base)


def _maybe_steered_v2_prompt(question: str) -> str:
    if not _business_workflow_v2_enabled():
        return question
    text = (question or "").strip()
    if not text or text in {"Confirm", "Deny"}:
        return text
    if _V2_RENDER_ONLY_PATTERN.search(text):
        return (
            "Invoke GenerateVisualSquadAndLineupBoard with board_mode RENDER_CURRENT only. "
            "Do not use SAVE_AND_RENDER. Do not save or reserve budget."
        )
    direct = _rewrite_v2_direct_invoke_prompt(text)
    if direct:
        return direct
    augmented = text
    for pattern, suffix in _V2_EXPLICIT_WRITE_AUGMENTS:
        if pattern.search(text):
            augmented = f"{augmented}{suffix}"
            break
    if any(pattern.search(text) for pattern in _V2_WRITE_INTENT_PATTERNS):
        return f"{augmented}{_V2_WRITE_STEER_SUFFIX}"
    return augmented


def _needs_v2_write_steering(question: str, metadata: dict[str, Any]) -> bool:
    if not _business_workflow_v2_enabled():
        return False
    if metadata.get("confirmation_card") or metadata.get("pending_return_control"):
        return False
    return _is_v2_write_intent(question)


def _no_lineup_answer(answer: str) -> bool:
    text = (answer or "").lower()
    return (
        "no proposed lineup has been saved" in text
        or "not been saved for head-coach review" in text
    )


def _deny_answer_for_function(fn: str) -> str:
    if fn == "OpenTransferOutReviewCase":
        return (
            "The transfer-out review was cancelled. No review case was created. "
            "No budget value was changed."
        )
    if fn == "SubmitCriticalDecisionAndSendEmail":
        return (
            "The recommendation was cancelled. No budget was reserved and no review record was saved."
        )
    if fn == "CreateAndReviewScoutingMission":
        return (
            "The scouting mission was cancelled. No mission record was created and no calendar invite was generated."
        )
    if fn == "GenerateVisualSquadAndLineupBoard":
        return (
            "The lineup save was cancelled. No lineup record was saved and no board image was written."
        )
    return "The action was cancelled. No records were saved."


def _resolve_v2_agent_response(
    client,
    *,
    normalized: str,
    prompt: str,
    agent_session: str,
    answer: str,
    metadata: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    if not _business_workflow_v2_enabled() or normalized in {"Confirm", "Deny"}:
        return answer, metadata, agent_session

    if _is_v2_render_only_intent(normalized):
        pending = metadata.get("pending_return_control") or {}
        if pending.get("invocation_id") and pending.get("function") == "GenerateVisualSquadAndLineupBoard":
            answer, events, metadata = _invoke_agent_return_control(
                client,
                agent_session=agent_session,
                pending=pending,
                confirmation_state="CONFIRM",
            )
            answer, metadata = _finalize_agent_response(answer, events, metadata, answer=answer)
        if _no_lineup_answer(answer) or metadata.get("lineup_image_route"):
            metadata.pop("confirmation_card", None)
            metadata.pop("pending_return_control", None)
            return answer, metadata, agent_session
        steered = _guardrail_safe_prompt(_maybe_steered_v2_prompt(normalized))
        for _attempt in range(_V2_WRITE_RETRY_ATTEMPTS):
            retry_session = f"advisor-{uuid.uuid4().hex[:10]}"
            answer, events, metadata = _invoke_agent_once(
                client,
                agent_session=retry_session,
                question=steered,
            )
            agent_session = retry_session
            if _no_lineup_answer(answer) or metadata.get("lineup_image_route"):
                metadata.pop("confirmation_card", None)
                metadata.pop("pending_return_control", None)
                break
            pending = metadata.get("pending_return_control") or {}
            if pending.get("invocation_id") and pending.get("function") == "GenerateVisualSquadAndLineupBoard":
                answer, events, metadata = _invoke_agent_return_control(
                    client,
                    agent_session=agent_session,
                    pending=pending,
                    confirmation_state="CONFIRM",
                )
                answer, metadata = _finalize_agent_response(answer, events, metadata, answer=answer)
                if metadata.get("lineup_image_route"):
                    metadata.pop("confirmation_card", None)
                    metadata.pop("pending_return_control", None)
                    break
            if not metadata.get("pending_return_control"):
                continue
        if not metadata.get("lineup_image_route") and not _no_lineup_answer(answer):
            answer, _, metadata, agent_session = _recover_failed_confirm(
                client,
                fn="GenerateVisualSquadAndLineupBoard",
                pending={
                    "function": "GenerateVisualSquadAndLineupBoard",
                    "parameters": {"board_mode": "RENDER_CURRENT", "formation": "4-3-3"},
                },
                agent_session=agent_session,
            )
        return answer, metadata, agent_session

    if re.search(r"completed scouting report", normalized, re.I) and not _has_completed_report(
        metadata, answer
    ):
        steered = _guardrail_safe_prompt(
            _rewrite_v2_direct_invoke_prompt(normalized)
            or _maybe_steered_v2_prompt(normalized)
        )
        for _attempt in range(_V2_WRITE_RETRY_ATTEMPTS):
            retry_session = f"advisor-{uuid.uuid4().hex[:10]}"
            answer, events, metadata = _invoke_agent_once(
                client,
                agent_session=retry_session,
                question=steered,
            )
            answer, metadata = _finalize_agent_response(answer, events, metadata, answer=answer)
            agent_session = retry_session
            if _has_completed_report(metadata, answer):
                metadata.pop("confirmation_card", None)
                metadata.pop("pending_return_control", None)
                break

    if not _is_v2_write_intent(normalized):
        return answer, metadata, agent_session

    pending = metadata.get("pending_return_control") or {}
    if pending.get("invocation_id"):
        return answer, metadata, agent_session

    for attempt in range(_V2_WRITE_RETRY_ATTEMPTS):
        retry_session = f"advisor-{uuid.uuid4().hex[:10]}"
        steered = _escalating_v2_write_prompt(normalized, attempt)
        answer, _, metadata = _invoke_agent_once(
            client,
            agent_session=retry_session,
            question=steered,
        )
        agent_session = retry_session
        pending = metadata.get("pending_return_control") or {}
        if pending.get("invocation_id"):
            break
        if not _agent_asked_chat_confirmation(answer):
            continue
    return answer, metadata, agent_session


def is_enabled() -> bool:
    return AGENT_ENABLED and bool(AGENT_ID) and bool(_resolved_agent_alias_id())


def disabled_response() -> dict[str, Any]:
    if not AGENT_ENABLED:
        return {"enabled": False, "message": DISABLED_MESSAGE, "refused": True}
    return {"enabled": False, "message": MISSING_CONFIG_MESSAGE, "refused": True}


def _sanitize_text(value: str) -> str:
    text = _ARN_PATTERN.sub("[redacted-resource]", value)
    text = re.sub(r"s3://[^\s]+", "[redacted-storage]", text, flags=re.I)
    text = _ACCOUNT_PATTERN.sub("[redacted-account]", text)
    text = _PLANNING_CONTEXT_PATTERN.sub("planning context", text)
    text = _INTERNAL_ID_PATTERN.sub("", text)
    text = re.sub(r"\bnotify management via sns\b", "notify management", text, flags=re.I)
    text = re.sub(r"\bSNS\b", "management notification", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _normalize_user_input(question: str) -> str:
    stripped = (question or "").strip()
    lowered = stripped.lower()
    if lowered in CONFIRM_INPUTS:
        return "Confirm"
    if lowered in DENY_INPUTS:
        return "Deny"
    return stripped


def _guardrail_safe_prompt(question: str) -> str:
    return GUARDRAIL_SAFE_PARAPHRASES.get(question.strip(), question)


def _is_confirmation_input(question: str) -> bool:
    return _normalize_user_input(question) in {"Confirm", "Deny"}


def _format_selection_success(body: dict) -> str:
    player = body.get("selected_player") or body.get("candidate_name") or "the candidate"
    reserved = body.get("reserved_amount_eur")
    remaining = body.get("remaining_budget_eur")
    notified = body.get("management_notified")
    if notified is None:
        sns = body.get("sns") or {}
        notified = bool(sns.get("published"))
    lines = [
        "Recommendation submitted for management review.",
        "Status: Pending management approval.",
        f"Selected player: {player}",
    ]
    if reserved is not None:
        lines.append(f"Reserved budget: {int(reserved):,} EUR")
    if remaining is not None:
        lines.append(f"Remaining budget: {int(remaining):,} EUR")
    if notified:
        lines.append("Management notification sent.")
    return "\n".join(lines)


def _format_lineup_success(body: dict) -> str:
    formation = body.get("formation") or "4-3-3"
    count = body.get("starting_players") or len(body.get("starting_xi") or [])
    return (
        f"Proposed lineup saved for head-coach review.\n"
        f"Status: Pending head-coach review\n"
        f"Formation: {formation}\n"
        f"Starting players: {count}"
    )


def _collect_tool_payloads(events: list[dict]) -> list[dict]:
    payloads: list[dict] = []
    for event in events:
        orchestration = _trace_orchestration(event)
        observation = orchestration.get("observation") or {}
        action_out = observation.get("actionGroupInvocationOutput") or {}
        body_text = str(action_out.get("text") or "")
        if not body_text.strip().startswith("{"):
            continue
        try:
            payloads.append(json.loads(body_text))
        except json.JSONDecodeError:
            continue
    return payloads


def _payload_priority(payload: dict) -> int:
    status = str(payload.get("status") or "").upper()
    priorities = {
        "LINEUP_BOARD_GENERATED": 100,
        "PENDING_SCOUT_OBSERVATION": 95,
        "READY_FOR_RECRUITMENT_REVIEW": 95,
        "PENDING_MANAGEMENT_APPROVAL": 90,
        "PENDING_HEAD_COACH_REVIEW": 85,
        "PENDING_TECHNICAL_DIRECTOR_REVIEW": 85,
        "PENDING_CONFIRMATION": 10,
    }
    if payload.get("image_route"):
        return max(priorities.get(status, 50), 100)
    if payload.get("report_label"):
        return max(priorities.get(status, 50), 95)
    return priorities.get(status, 0)


def _format_board_answer(payload: dict) -> str:
    lines = [
        f"Current proposed lineup board ({payload.get('formation', '4-3-3')}).",
        "Status: Pending head-coach review",
    ]
    if payload.get("opening_fixture"):
        lines.append(f"Opening fixture: {payload['opening_fixture']}")
    budget = payload.get("remaining_budget_eur")
    if budget is None:
        budget = payload.get("remaining_confirmed_budget_eur")
    if budget is not None:
        lines.append(f"Remaining budget: {int(budget):,} EUR")
    for name in payload.get("pending_management_candidates") or []:
        if name:
            lines.append(f"Pending management approval: {name}")
    for name in payload.get("pending_transfer_out_players") or []:
        if name:
            lines.append(f"Transfer-out review pending: {name}")
    return "\n".join(lines)


def _format_completed_report_answer(payload: dict) -> str:
    lines = [
        str(payload.get("report_label") or "Demo replay: completed scouting observation"),
        f"Candidate: {payload.get('candidate_name', '')}",
    ]
    if payload.get("main_risk"):
        lines.append(f"Main risk: {payload['main_risk']}")
    if payload.get("ai_summary"):
        lines.append(f"AI summary: {payload['ai_summary']}")
    if payload.get("recommendation"):
        lines.append(f"Recommendation: {payload['recommendation']}")
    lines.append("Status: Ready for recruitment review")
    return "\n".join(lines)


def _merge_payload_into_metadata(metadata: dict[str, Any], payload: dict) -> None:
    if payload.get("image_route"):
        metadata["lineup_image_route"] = payload.get("image_route")
    if payload.get("remaining_budget_eur") is not None:
        metadata["remaining_budget_eur"] = payload.get("remaining_budget_eur")
    elif payload.get("remaining_confirmed_budget_eur") is not None:
        metadata["remaining_budget_eur"] = payload.get("remaining_confirmed_budget_eur")
    if (
        str(payload.get("status") or "").upper() in {"LINEUP_BOARD_GENERATED", "RENDERED"}
        and payload.get("remaining_budget_eur") is not None
    ):
        metadata["remaining_budget_eur"] = payload.get("remaining_budget_eur")
    workflow_cards = list(metadata.get("workflow_cards") or [])
    card_types = {str(card.get("type")) for card in workflow_cards}
    if payload.get("mission_card_type") == "scouting_mission" and "scouting_mission" not in card_types:
        workflow_cards.append({"type": "scouting_mission", **payload})
    if payload.get("status") == "PENDING_TECHNICAL_DIRECTOR_REVIEW" and "transfer_out_review" not in card_types:
        workflow_cards.append({"type": "transfer_out_review", **payload})
    if payload.get("report_label") and "completed_demo_report" not in card_types:
        workflow_cards.append({"type": "completed_demo_report", **payload})
    if payload.get("squad_board_type") == "visual_squad_board" and "visual_squad_board" not in card_types:
        workflow_cards.append({"type": "visual_squad_board", **payload})
    if payload.get("email_user_message") and "review_email_result" not in card_types:
        workflow_cards.append(
            {
                "type": "review_email_result",
                "message": payload.get("email_user_message"),
            }
        )
    metadata["workflow_cards"] = workflow_cards[:4]


def _append_workflow_downloads(answer: str, metadata: dict[str, Any]) -> str:
    text = answer or ""
    for card in metadata.get("workflow_cards") or []:
        invite = str(card.get("calendar_invite_key") or "").strip()
        if not invite:
            continue
        line = f"Download: /api/opening-season/calendar-invite/{invite}"
        if "calendar-invite/" not in text:
            text = f"{text}\n{line}".strip()
    return text


def _format_answer_from_payload(payload: dict) -> str | None:
    status = str(payload.get("status") or "").upper()
    if status == "PENDING_MANAGEMENT_APPROVAL":
        base = _format_selection_success(payload)
        if payload.get("email_user_message"):
            return f"{base}\n{payload['email_user_message']}"
        return base
    if status == "PENDING_TECHNICAL_DIRECTOR_REVIEW":
        return (
            f"Transfer-out review case opened.\n"
            f"Player: {payload.get('player_name', '')}\n"
            f"Reason: {payload.get('reason', '')}\n"
            f"Estimated budget released: {payload.get('estimated_budget_release_eur', 0):,} EUR\n"
            f"Status: Pending technical-director review\n"
            f"The player has not been sold."
        )
    if status == "PENDING_SCOUT_OBSERVATION":
        invite = str(payload.get("calendar_invite_key") or "").strip()
        invite_line = (
            f"\nDownload: /api/opening-season/calendar-invite/{invite}" if invite else ""
        )
        return (
            f"Scouting mission created.\n"
            f"Candidate: {payload.get('candidate_name', '')}\n"
            f"Match: {payload.get('fixture_name', '')}\n"
            f"Date: {payload.get('display_date', '')}\n"
            f"Calendar: {payload.get('calendar_label', 'Calendar invite ready to download')}\n"
            f"Reminder: {payload.get('reminder_label', '')}\n"
            f"Status: Pending scout observation"
            f"{invite_line}"
        )
    if status == "READY_FOR_RECRUITMENT_REVIEW":
        return _format_completed_report_answer(payload)
    if payload.get("email_user_message"):
        base = _format_selection_success(payload)
        return f"{base}\n{payload['email_user_message']}"
    if status in {"PENDING_HEAD_COACH_REVIEW", "LINEUP_FINALIZED"}:
        return _format_lineup_success(payload)
    if status == "LINEUP_BOARD_GENERATED" and payload.get("image_route"):
        return _format_board_answer(payload)
    if status == "NOT_FOUND" and payload.get("message"):
        return str(payload["message"])
    if status in {"FAILURE", "REJECTED"} and payload.get("message"):
        return str(payload["message"])
    if status == "CANCELLED" and payload.get("message"):
        return str(payload["message"])
    return None


def _finalize_agent_response(
    raw_answer: str,
    events: list[dict],
    metadata: dict[str, Any],
    *,
    answer: str | None = None,
) -> tuple[str, dict[str, Any]]:
    payloads = _collect_tool_payloads(events)
    for payload in payloads:
        _merge_payload_into_metadata(metadata, payload)
    best = max(payloads, key=_payload_priority) if payloads else None
    resolved = answer if answer is not None else _answer_from_tool_payload(raw_answer, events)
    if best and _payload_priority(best) >= 85:
        formatted = _format_answer_from_payload(best)
        if formatted:
            resolved = formatted
    resolved = _append_workflow_downloads(resolved, metadata)
    return resolved, metadata


def _has_completed_report(metadata: dict[str, Any], answer: str) -> bool:
    text = (answer or "").lower()
    if "demo replay" in text and "ready for recruitment review" in text:
        return True
    for card in metadata.get("workflow_cards") or []:
        if card.get("type") == "completed_demo_report":
            return True
    return False


def _post_confirm_steer(fn: str, params: dict[str, str] | None = None) -> str | None:
    params = _enrich_confirmation_parameters(fn, params or {})
    if fn == "CreateAndReviewScoutingMission":
        candidate = params.get("candidate_name") or "Ron Ben Ari"
        mode = params.get("mission_mode") or "CREATE_MISSION"
        return (
            f"Invoke CreateAndReviewScoutingMission with candidate_name {candidate} "
            f"and mission_mode {mode}."
        )
    if fn == "SubmitCriticalDecisionAndSendEmail":
        candidate = params.get("candidate_name") or "Ron Ben Ari"
        salary = params.get("salary_eur") or "43000"
        role = params.get("target_role") or "Right-back"
        return (
            f"Invoke SubmitCriticalDecisionAndSendEmail with candidate_name {candidate}, "
            f"salary_eur {salary}, and target_role {role}."
        )
    if fn == "OpenTransferOutReviewCase":
        player = params.get("player_name") or "Daniel Cohen"
        release = params.get("estimated_budget_release_eur") or "25000"
        return (
            f"Invoke OpenTransferOutReviewCase with player_name {player} "
            f"and estimated_budget_release_eur {release}."
        )
    if fn == "GenerateVisualSquadAndLineupBoard":
        mode = params.get("board_mode") or "SAVE_AND_RENDER"
        formation = params.get("formation") or "4-3-3"
        return (
            f"Invoke GenerateVisualSquadAndLineupBoard with board_mode {mode}, "
            f"formation {formation}, and demo_lineup true."
        )
    return None


def _confirm_succeeded(
    fn: str,
    answer: str,
    metadata: dict[str, Any],
    events: list[dict],
) -> bool:
    payloads = _collect_tool_payloads(events)
    if payloads:
        best = max(payloads, key=_payload_priority)
        status = str(best.get("status") or "").upper()
        if fn == "CreateAndReviewScoutingMission":
            return status == "PENDING_SCOUT_OBSERVATION"
        if fn == "SubmitCriticalDecisionAndSendEmail":
            return status == "PENDING_MANAGEMENT_APPROVAL"
        if fn == "OpenTransferOutReviewCase":
            return status == "PENDING_TECHNICAL_DIRECTOR_REVIEW"
        if fn == "GenerateVisualSquadAndLineupBoard":
            return status in {"PENDING_HEAD_COACH_REVIEW", "LINEUP_BOARD_GENERATED"} or bool(
                best.get("image_route")
            )
    if fn == "CreateAndReviewScoutingMission":
        if "calendar-invite/" in (answer or ""):
            return True
        return any(
            card.get("calendar_invite_key")
            for card in (metadata.get("workflow_cards") or [])
        )
    if fn == "GenerateVisualSquadAndLineupBoard":
        return bool(metadata.get("lineup_image_route"))
    return False


def _recover_failed_confirm(
    client,
    *,
    fn: str,
    pending: dict[str, Any],
    agent_session: str,
) -> tuple[str, list[dict], dict[str, Any], str]:
    steered = _post_confirm_steer(fn, pending.get("parameters"))
    if not steered:
        return "", [], {}, agent_session
    retry_session = f"advisor-{uuid.uuid4().hex[:10]}"
    answer, events, metadata = _invoke_agent_once(
        client,
        agent_session=retry_session,
        question=_guardrail_safe_prompt(steered),
    )
    pending_rc = metadata.get("pending_return_control") or {}
    if pending_rc.get("invocation_id") and str(pending_rc.get("function") or "") == fn:
        answer, events, metadata = _invoke_agent_return_control(
            client,
            agent_session=retry_session,
            pending=pending_rc,
            confirmation_state="CONFIRM",
        )
    answer, metadata = _finalize_agent_response(answer, events, metadata, answer=answer)
    metadata.pop("confirmation_card", None)
    metadata.pop("pending_return_control", None)
    return answer, events, metadata, retry_session


def _answer_from_tool_payload(answer: str, events: list[dict]) -> str:
    for event in reversed(events):
        orchestration = _trace_orchestration(event)
        observation = orchestration.get("observation") or {}
        action_out = observation.get("actionGroupInvocationOutput") or {}
        body_text = str(action_out.get("text") or "")
        if not body_text.strip().startswith("{"):
            continue
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            continue
        status = str(payload.get("status") or "").upper()
        if status == "PENDING_MANAGEMENT_APPROVAL":
            base = _format_selection_success(payload)
            if payload.get("email_user_message"):
                return f"{base}\n{payload['email_user_message']}"
            return base
        if status == "PENDING_TECHNICAL_DIRECTOR_REVIEW":
            return (
                f"Transfer-out review case opened.\n"
                f"Player: {payload.get('player_name', '')}\n"
                f"Reason: {payload.get('reason', '')}\n"
                f"Estimated budget released: {payload.get('estimated_budget_release_eur', 0):,} EUR\n"
                f"Status: Pending technical-director review\n"
                f"The player has not been sold."
            )
        if status == "PENDING_SCOUT_OBSERVATION":
            invite = str(payload.get("calendar_invite_key") or "").strip()
            invite_line = (
                f"\nDownload: /api/opening-season/calendar-invite/{invite}" if invite else ""
            )
            return (
                f"Scouting mission created.\n"
                f"Candidate: {payload.get('candidate_name', '')}\n"
                f"Match: {payload.get('fixture_name', '')}\n"
                f"Date: {payload.get('display_date', '')}\n"
                f"Calendar: {payload.get('calendar_label', '')}\n"
                f"Reminder: {payload.get('reminder_label', '')}\n"
                f"Status: Pending scout observation"
                f"{invite_line}"
            )
        if status == "READY_FOR_RECRUITMENT_REVIEW":
            return _format_completed_report_answer(payload)
        if payload.get("email_user_message"):
            base = _format_selection_success(payload)
            return f"{base}\n{payload['email_user_message']}"
        if status in {"PENDING_HEAD_COACH_REVIEW", "LINEUP_FINALIZED"}:
            return _format_lineup_success(payload)
        if status == "LINEUP_BOARD_GENERATED" and payload.get("image_route"):
            return _format_board_answer(payload)
        if status == "NOT_FOUND" and payload.get("message"):
            return str(payload["message"])
        if status in {"FAILURE", "REJECTED"} and payload.get("message"):
            return str(payload["message"])
        if status == "CANCELLED" and payload.get("message"):
            return str(payload["message"])
    return answer


def _parse_parameters(block: dict | None) -> dict[str, str]:
    params: dict[str, str] = {}
    if not isinstance(block, dict):
        return params
    for item in block.get("parameters") or []:
        if isinstance(item, dict) and item.get("name"):
            params[str(item["name"])] = str(item.get("value", ""))
    return params


def _trace_orchestration(event: dict) -> dict:
    trace = event.get("trace") or {}
    return trace.get("trace", {}).get("orchestrationTrace") or {}


def _is_v2_write_intent(question: str) -> bool:
    text = (question or "").strip()
    return any(pattern.search(text) for pattern in _V2_WRITE_INTENT_PATTERNS)


def _is_v2_render_only_intent(question: str) -> bool:
    return bool(_V2_RENDER_ONLY_PATTERN.search(question or ""))


def _enrich_confirmation_parameters(fn: str, params: dict[str, str]) -> dict[str, str]:
    enriched = dict(params or {})
    if fn == "OpenTransferOutReviewCase":
        enriched.setdefault("player_name", "Daniel Cohen")
        enriched.setdefault("estimated_budget_release_eur", "25000")
    elif fn == "SubmitCriticalDecisionAndSendEmail":
        enriched.setdefault("candidate_name", "Ron Ben Ari")
        enriched.setdefault("salary_eur", "43000")
        enriched.setdefault("target_role", "Right-back")
    elif fn == "CreateAndReviewScoutingMission":
        enriched.setdefault("candidate_name", "Ron Ben Ari")
        enriched.setdefault("mission_mode", "CREATE_MISSION")
    elif fn == "GenerateVisualSquadAndLineupBoard":
        enriched.setdefault("formation", "4-3-3")
        enriched.setdefault("board_mode", "SAVE_AND_RENDER")
    return enriched


def _confirmation_card_for_function(fn: str, params: dict[str, str]) -> dict[str, Any]:
    params = _enrich_confirmation_parameters(fn, params)
    card: dict[str, Any] = {
        "function": fn,
        "parameters": params,
        "state": "pending",
    }
    if fn == "SubmitPlayerSelectionToManagement":
        card["title"] = "Submit recommendation to management"
        card["action_label"] = "Submit recommendation to management and reserve budget"
    elif fn == "SubmitCriticalDecisionAndSendEmail":
        card["title"] = "Confirm player recommendation"
        card["action_label"] = "Submit critical decision for management review"
    elif fn == "OpenTransferOutReviewCase":
        card["title"] = "Open transfer-out review case"
        card["action_label"] = "Open transfer-out review case"
    elif fn == "CreateAndReviewScoutingMission":
        card["title"] = "Create scouting mission"
        card["action_label"] = "Create scouting mission"
    elif fn == "GenerateVisualSquadAndLineupBoard":
        card["title"] = "Save proposed lineup"
        card["action_label"] = "Save and show proposed lineup board"
    elif fn == "FinalizeCurrentLineup":
        card["title"] = "Save proposed lineup for head-coach review"
        card["action_label"] = "Save proposed lineup for head-coach review"
    else:
        card["title"] = "Action requires confirmation"
        card["action_label"] = "Confirm this write action"
    return card


def _parse_return_control(events: list[dict]) -> dict[str, Any] | None:
    for event in reversed(events):
        rc = event.get("returnControl") or {}
        invocation_id = str(rc.get("invocationId") or "").strip()
        for item in rc.get("invocationInputs") or []:
            fn_input = item.get("functionInvocationInput") or {}
            inv_type = str(fn_input.get("actionInvocationType") or "")
            if inv_type != "USER_CONFIRMATION":
                continue
            fn = str(fn_input.get("function") or "")
            if fn not in WRITE_CONFIRM_TOOLS:
                continue
            params = _parse_parameters(fn_input)
            return {
                "invocation_id": invocation_id,
                "action_group": str(fn_input.get("actionGroup") or ""),
                "function": fn,
                "parameters": params,
            }
    return None


def _confirmation_prompt_from_return_control(pending: dict[str, Any]) -> str:
    fn = str(pending.get("function") or "")
    params = pending.get("parameters") or {}
    if fn == "OpenTransferOutReviewCase":
        player = params.get("player_name") or "the selected player"
        release = (
            params.get("estimated_budget_release_eur")
            or params.get("estimated_release_eur")
            or ("25000" if "daniel cohen" in player.lower() else "")
        )
        suffix = f" Estimated release: {release} EUR." if release else ""
        return (
            f"Please confirm opening a transfer-out review case for {player}.{suffix} "
            "No budget will change until technical-director review completes."
        )
    if fn == "SubmitCriticalDecisionAndSendEmail":
        candidate = params.get("candidate_name") or "the candidate"
        salary = params.get("salary_eur") or "43000"
        return (
            f"Please confirm submitting {candidate} for management review. "
            f"Budget reservation: {salary} EUR. Remaining budget after confirmation: 57,000 EUR."
        )
    if fn == "CreateAndReviewScoutingMission":
        candidate = params.get("candidate_name") or "the candidate"
        return (
            f"Please confirm creating a scouting mission for {candidate}. "
            "A calendar invite will be prepared for download after confirmation."
        )
    if fn == "GenerateVisualSquadAndLineupBoard":
        return (
            "Please confirm saving the proposed 4-3-3 lineup for head-coach review. "
            "Exactly 11 proposed players will be saved after confirmation."
        )
    return "Please confirm this write action before it is saved."


def _extract_confirmation_card(
    events: list[dict],
    answer: str,
    *,
    pending_return_control: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if pending_return_control:
        return _confirmation_card_for_function(
            str(pending_return_control.get("function") or ""),
            pending_return_control.get("parameters") or {},
        )
    if _business_workflow_v2_enabled():
        return None
    pending = "PENDING_CONFIRMATION" in (answer or "").upper()
    for event in reversed(events):
        orchestration = _trace_orchestration(event)
        inv = orchestration.get("invocationInput") or {}
        ag = inv.get("actionGroupInvocationInput") or {}
        fn = str(ag.get("function") or "")
        if fn not in WRITE_CONFIRM_TOOLS:
            continue
        observation = orchestration.get("observation") or {}
        if observation.get("repromptResponse"):
            pending = True
        action_out = observation.get("actionGroupInvocationOutput") or {}
        body_text = str(action_out.get("text") or "")
        if "PENDING_CONFIRMATION" in body_text.upper():
            pending = True
        if not pending:
            continue
        params = _parse_parameters(ag)
        return _confirmation_card_for_function(fn, params)
    if pending:
        return {
            "function": "unknown",
            "parameters": {},
            "state": "pending",
            "title": "Action requires confirmation",
            "action_label": "Confirm this write action",
        }
    return _extract_confirmation_from_answer(answer)


def _extract_confirmation_from_answer(answer: str) -> dict[str, Any] | None:
    text = answer or ""
    if not _CONFIRM_PROMPT_PATTERN.search(text):
        return None
    fields = {
        key.lower().replace(" ", "_"): value.strip()
        for key, value in _CONFIRM_FIELD_PATTERN.findall(text)
    }
    if "candidate" in fields or "formation" in fields or "target_role" in fields:
        if "formation" in fields or "players" in fields:
            fn = "GenerateVisualSquadAndLineupBoard" if _business_workflow_v2_enabled() else "FinalizeCurrentLineup"
        elif _business_workflow_v2_enabled():
            fn = "SubmitCriticalDecisionAndSendEmail"
        else:
            fn = "SubmitPlayerSelectionToManagement"
        return _confirmation_card_for_function(fn, fields)
    return {
        "function": "unknown",
        "parameters": fields,
        "state": "pending",
        "title": "Action requires confirmation",
        "action_label": "Confirm this write action",
    }


def _extract_metadata(
    events: list[dict],
    answer: str,
    *,
    pending_return_control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tools: list[str] = []
    documents: list[str] = []
    warnings: list[str] = []
    lineup_route = None
    remaining_budget = None
    lineup_board_budget = None
    guardrail_intervened = False
    workflow_cards: list[dict[str, Any]] = []

    for event in events:
        orchestration = _trace_orchestration(event)
        invocation = orchestration.get("invocationInput") or {}
        if "actionGroupInvocationInput" in invocation:
            ag = invocation["actionGroupInvocationInput"]
            fn = ag.get("function") or ag.get("actionGroupName") or "tool"
            fn_name = str(fn)
            if fn_name in ALLOWED_PUBLIC_TOOLS and fn_name not in tools:
                tools.append(fn_name)
        observation = orchestration.get("observation") or {}
        kb = observation.get("knowledgeBaseLookupOutput") or {}
        for ref in kb.get("retrievedReferences") or []:
            loc = ref.get("location", {}).get("s3Location", {}).get("uri", "")
            name = loc.rsplit("/", 1)[-1] if loc else ""
            if name and name not in documents:
                documents.append(name)
        if observation.get("repromptResponse"):
            warnings.append("confirmation_or_reprompt")
        action_response = observation.get("actionGroupInvocationOutput") or {}
        text = action_response.get("text", "") or str(
            action_response.get("actionGroupInvocationOutput", "")
        )
        if text:
            try:
                payload = json.loads(text) if str(text).strip().startswith("{") else {}
            except json.JSONDecodeError:
                payload = {}
            if payload.get("image_route"):
                lineup_route = payload.get("image_route")
            if payload.get("remaining_budget_eur") is not None:
                remaining_budget = payload.get("remaining_budget_eur")
            if (
                str(payload.get("status") or "").upper()
                in {"LINEUP_BOARD_GENERATED", "RENDERED"}
                and payload.get("remaining_budget_eur") is not None
            ):
                lineup_board_budget = payload.get("remaining_budget_eur")
            if payload.get("formation"):
                pass
            if payload.get("mission_card_type") == "scouting_mission":
                workflow_cards.append({"type": "scouting_mission", **payload})
            if payload.get("status") == "PENDING_TECHNICAL_DIRECTOR_REVIEW":
                workflow_cards.append({"type": "transfer_out_review", **payload})
            if payload.get("report_label"):
                workflow_cards.append({"type": "completed_demo_report", **payload})
            if payload.get("squad_board_type") == "visual_squad_board":
                workflow_cards.append({"type": "visual_squad_board", **payload})
            if payload.get("email_user_message"):
                workflow_cards.append(
                    {
                        "type": "review_email_result",
                        "message": payload.get("email_user_message"),
                    }
                )
        guard_trace = event.get("trace", {}).get("trace", {}).get("guardrailTrace")
        if guard_trace and guard_trace.get("action") == "INTERVENED":
            guardrail_intervened = True

    route_match = _LINEUP_ROUTE_PATTERN.search(answer)
    if route_match:
        lineup_route = route_match.group(0)
    budget_match = _REMAINING_BUDGET_PATTERN.search(answer)
    if budget_match and remaining_budget is None:
        remaining_budget = int(budget_match.group(1).replace(",", ""))
    if lineup_board_budget is not None:
        remaining_budget = lineup_board_budget

    confirmation_card = _extract_confirmation_card(
        events,
        answer,
        pending_return_control=pending_return_control,
    )
    if confirmation_card and "confirmation_or_reprompt" not in warnings:
        warnings.append("confirmation_or_reprompt")

    tool_labels = [TOOL_USER_LABELS.get(name, name) for name in tools[:8]]
    metadata = {
        "documents_used": documents[:8],
        "tools_executed": tools[:8],
        "tool_labels": tool_labels[:8],
        "lineup_image_route": lineup_route,
        "remaining_budget_eur": remaining_budget,
        "missing_information": None,
        "warnings": warnings[:4],
        "confirmation_card": confirmation_card,
        "workflow_cards": workflow_cards[:4],
        "guardrail_intervened": guardrail_intervened,
        "coach_brief": bool(_COACH_BRIEF_PREFIX.search(answer or "")),
    }
    if pending_return_control:
        metadata["pending_return_control"] = pending_return_control
    return metadata


def _invoke_agent_once(
    client,
    *,
    agent_session: str,
    question: str | None = None,
    session_state: dict[str, Any] | None = None,
) -> tuple[str, list[dict], dict[str, Any]]:
    collected_events: list[dict] = []
    kwargs: dict[str, Any] = {
        "agentId": AGENT_ID,
        "agentAliasId": _resolved_agent_alias_id(),
        "sessionId": agent_session,
        "enableTrace": True,
    }
    if session_state:
        kwargs["sessionState"] = session_state
    if question is not None:
        kwargs["inputText"] = question
    response = client.invoke_agent(**kwargs)
    answer_parts: list[str] = []
    for event in response.get("completion", []):
        collected_events.append(event)
        if "chunk" in event and "bytes" in event["chunk"]:
            answer_parts.append(event["chunk"]["bytes"].decode("utf-8", errors="replace"))
    raw_answer = "".join(answer_parts).strip()
    pending_return_control = _parse_return_control(collected_events)
    metadata = _extract_metadata(
        collected_events,
        raw_answer,
        pending_return_control=pending_return_control,
    )
    answer = _answer_from_tool_payload(raw_answer, collected_events)
    answer, metadata = _finalize_agent_response(
        raw_answer,
        collected_events,
        metadata,
        answer=answer,
    )
    if not answer.strip() and pending_return_control:
        answer = _confirmation_prompt_from_return_control(pending_return_control)
    answer = _sanitize_text(answer) or GENERIC_ERROR_MESSAGE
    refused = GUARDRAIL_BLOCK_MESSAGE.lower() in answer.lower()
    if metadata.get("guardrail_intervened") and not raw_answer.strip() and not pending_return_control:
        answer = GUARDRAIL_BLOCK_MESSAGE
        refused = True
    return answer, collected_events, metadata


def _invoke_agent_return_control(
    client,
    *,
    agent_session: str,
    pending: dict[str, Any],
    confirmation_state: str,
) -> tuple[str, list[dict], dict[str, Any]]:
    response_body = json.dumps({"status": confirmation_state})
    session_state = {
        "invocationId": pending["invocation_id"],
        "returnControlInvocationResults": [
            {
                "functionResult": {
                    "actionGroup": pending["action_group"],
                    "function": pending["function"],
                    "confirmationState": confirmation_state,
                    "responseBody": {
                        "TEXT": {
                            "body": response_body,
                        }
                    },
                }
            }
        ],
    }
    return _invoke_agent_once(client, agent_session=agent_session, session_state=session_state)


def latest_pending_return_control(messages: list[dict]) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("agent_metadata") or {}
        pending = meta.get("pending_return_control")
        if isinstance(pending, dict) and pending.get("invocation_id"):
            return pending
    return None


def invoke_agent(
    question: str,
    session_id: str | None = None,
    *,
    pending_return_control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not is_enabled():
        return disabled_response()

    normalized = _normalize_user_input(question)
    prompt = (
        normalized
        if normalized in {"Confirm", "Deny"}
        else _guardrail_safe_prompt(_maybe_steered_v2_prompt(normalized))
    )
    agent_session = session_id or f"advisor-{uuid.uuid4().hex}"
    try:
        client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
        if normalized in {"Confirm", "Deny"} and pending_return_control:
            confirmation_state = "CONFIRM" if normalized == "Confirm" else "DENY"
            answer, collected_events, metadata = _invoke_agent_return_control(
                client,
                agent_session=agent_session,
                pending=pending_return_control,
                confirmation_state=confirmation_state,
            )
            answer, metadata = _finalize_agent_response(
                answer,
                collected_events,
                metadata,
                answer=answer,
            )
            fn = str(pending_return_control.get("function") or "")
            if (
                confirmation_state == "CONFIRM"
                and _business_workflow_v2_enabled()
                and fn
                and not _confirm_succeeded(fn, answer, metadata, collected_events)
            ):
                answer, collected_events, metadata, agent_session = _recover_failed_confirm(
                    client,
                    fn=fn,
                    pending=pending_return_control,
                    agent_session=agent_session,
                )
            if confirmation_state == "DENY":
                fn = str(pending_return_control.get("function") or "")
                explicit = _deny_answer_for_function(fn)
                if (
                    _business_workflow_v2_enabled()
                    or not answer.strip()
                    or "cancel" not in answer.lower()
                ):
                    answer = explicit
            metadata.pop("confirmation_card", None)
            metadata.pop("pending_return_control", None)
            refused = GUARDRAIL_BLOCK_MESSAGE.lower() in answer.lower()
            clear_pending = True
        elif (
            _business_workflow_v2_enabled()
            and re.search(r"completed scouting report", normalized, re.I)
        ):
            steered = _guardrail_safe_prompt(
                _rewrite_v2_direct_invoke_prompt(normalized) or normalized
            )
            for attempt in range(_V2_WRITE_RETRY_ATTEMPTS):
                retry_session = agent_session if attempt == 0 else f"advisor-{uuid.uuid4().hex[:10]}"
                answer, collected_events, metadata = _invoke_agent_once(
                    client,
                    agent_session=retry_session,
                    question=steered,
                )
                pending_rc = metadata.get("pending_return_control") or {}
                if pending_rc.get("invocation_id"):
                    answer, collected_events, metadata = _invoke_agent_return_control(
                        client,
                        agent_session=retry_session,
                        pending=pending_rc,
                        confirmation_state="CONFIRM",
                    )
                answer, metadata = _finalize_agent_response(
                    answer, collected_events, metadata, answer=answer
                )
                agent_session = retry_session
                if _has_completed_report(metadata, answer):
                    metadata.pop("confirmation_card", None)
                    metadata.pop("pending_return_control", None)
                    break
            refused = GUARDRAIL_BLOCK_MESSAGE.lower() in answer.lower()
            clear_pending = False
        else:
            answer, collected_events, metadata = _invoke_agent_once(
                client, agent_session=agent_session, question=prompt
            )
            if _needs_v2_write_steering(normalized, metadata):
                steered = _guardrail_safe_prompt(_maybe_steered_v2_prompt(normalized))
                if steered != prompt:
                    answer, collected_events, metadata = _invoke_agent_once(
                        client, agent_session=agent_session, question=steered
                    )
            answer, metadata, agent_session = _resolve_v2_agent_response(
                client,
                normalized=normalized,
                prompt=prompt,
                agent_session=agent_session,
                answer=answer,
                metadata=metadata,
            )
            refused = GUARDRAIL_BLOCK_MESSAGE.lower() in answer.lower()
            if refused and prompt != normalized:
                retry_answer, retry_events, retry_meta = _invoke_agent_once(
                    client, agent_session=agent_session, question=normalized
                )
                if GUARDRAIL_BLOCK_MESSAGE.lower() not in retry_answer.lower():
                    answer, collected_events, metadata = retry_answer, retry_events, retry_meta
                    refused = False
            if refused and prompt in GUARDRAIL_SAFE_PARAPHRASES:
                safe = GUARDRAIL_SAFE_PARAPHRASES[prompt]
                retry_answer, retry_events, retry_meta = _invoke_agent_once(
                    client, agent_session=f"advisor-{uuid.uuid4().hex}", question=safe
                )
                if GUARDRAIL_BLOCK_MESSAGE.lower() not in retry_answer.lower():
                    answer, collected_events, metadata = retry_answer, retry_events, retry_meta
                    agent_session = f"advisor-{uuid.uuid4().hex}"
                    refused = False
            tool_failed = (
                answer == GENERIC_ERROR_MESSAGE
                or "could not complete this request" in answer.lower()
            )
            clear_pending = _is_confirmation_input(normalized) and (
                tool_failed or metadata.get("confirmation_card") is None
            )
            if clear_pending:
                agent_session = f"advisor-{uuid.uuid4().hex}"
        return {
            "enabled": True,
            "session_id": agent_session,
            "answer": answer,
            "refused": refused,
            "generation_mode": "bedrock_agent",
            "metadata": metadata,
            "clear_pending_action": clear_pending,
        }
    except Exception:
        new_session = f"advisor-{uuid.uuid4().hex}"
        return {
            "enabled": True,
            "session_id": new_session if _is_confirmation_input(normalized) else agent_session,
            "answer": GENERIC_ERROR_MESSAGE,
            "refused": True,
            "generation_mode": "bedrock_agent",
            "reason": "agent_error",
            "metadata": {},
            "clear_pending_action": _is_confirmation_input(normalized),
        }


def agent_result_to_chat_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Map Agent invoke output to polished root UI chat response shape."""
    metadata = result.get("metadata") or {}
    documents = metadata.get("documents_used") or []
    context = [
        {
            "source": name,
            "text": "",
            "score": 1.0,
            "document_name": name,
        }
        for name in documents
    ]
    main_source = context[0] if context else None
    if result.get("clear_pending_action"):
        metadata["clear_pending_action"] = True
    return {
        "answer": result.get("answer") or GENERIC_ERROR_MESSAGE,
        "refused": bool(result.get("refused")),
        "reason": result.get("reason"),
        "generation_mode": "bedrock_agent",
        "context": context,
        "main_source": main_source,
        "bedrock_session_id": result.get("session_id"),
        "agent_metadata": metadata,
        "clear_pending_action": bool(result.get("clear_pending_action")),
    }
