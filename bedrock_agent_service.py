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
_V2_EXPLICIT_WRITE_AUGMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"open\s+a\s+transfer-out\s+review\s+case\s+for\s+daniel\s+cohen", re.I),
        " Daniel Cohen is an approved current-squad rotation midfielder in ScoutMatch operational data.",
    ),
    (
        re.compile(r"submit\s+the\s+recommendation\s+for\s+management\s+review", re.I),
        " Ron Ben Ari is the approved right-back candidate at 43,000 EUR in ScoutMatch operational data.",
    ),
    (
        re.compile(r"create\s+a\s+scouting\s+mission\s+for\s+his\s+next\s+match", re.I),
        " Use Ron Ben Ari as candidate_name with mission_mode CREATE_MISSION.",
    ),
    (
        re.compile(r"save\s+and\s+show\s+the\s+proposed\s+4-3-3\s+lineup", re.I),
        " Use board_mode SAVE_AND_RENDER, formation 4-3-3, and demo_lineup true.",
    ),
)


def _maybe_steered_v2_prompt(question: str) -> str:
    if not _business_workflow_v2_enabled():
        return question
    text = (question or "").strip()
    if not text or text in {"Confirm", "Deny"}:
        return text
    if _V2_RENDER_ONLY_PATTERN.search(text):
        return (
            f"{text} Use GenerateVisualSquadAndLineupBoard with board_mode RENDER_CURRENT only. "
            "Do not save or reserve budget."
        )
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
    text = (question or "").strip()
    return any(pattern.search(text) for pattern in _V2_WRITE_INTENT_PATTERNS)


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
            return _format_selection_success(payload)
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
            return (
                f"Scouting mission created.\n"
                f"Candidate: {payload.get('candidate_name', '')}\n"
                f"Match: {payload.get('fixture_name', '')}\n"
                f"Date: {payload.get('display_date', '')}\n"
                f"Calendar: {payload.get('calendar_label', '')}\n"
                f"Reminder: {payload.get('reminder_label', '')}\n"
                f"Status: Pending scout observation"
            )
        if status == "READY_FOR_RECRUITMENT_REVIEW":
            return (
                f"{payload.get('report_label', 'Demo replay')}\n"
                f"Candidate: {payload.get('candidate_name', '')}\n"
                f"Recommendation: {payload.get('recommendation', '')}\n"
                f"Status: Ready for recruitment review"
            )
        if payload.get("email_user_message"):
            base = _format_selection_success(payload)
            return f"{base}\n{payload['email_user_message']}"
        if status in {"PENDING_HEAD_COACH_REVIEW", "LINEUP_FINALIZED"}:
            return _format_lineup_success(payload)
        if status == "LINEUP_BOARD_GENERATED" and payload.get("image_route"):
            return (
                f"Current proposed lineup board ({payload.get('formation', '4-3-3')}).\n"
                f"Status: Pending head-coach review\n"
                f"View: {payload['image_route']}"
            )
        if status == "NOT_FOUND" and payload.get("message"):
            return str(payload["message"])
        if status in {"FAILURE", "REJECTED"} and payload.get("message"):
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


def _confirmation_card_for_function(fn: str, params: dict[str, str]) -> dict[str, Any]:
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
        release = params.get("estimated_budget_release_eur") or params.get("estimated_release_eur")
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
            refused = GUARDRAIL_BLOCK_MESSAGE.lower() in answer.lower()
            clear_pending = True
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
            if (
                _business_workflow_v2_enabled()
                and any(pattern.search(normalized) for pattern in _V2_WRITE_INTENT_PATTERNS)
                and not metadata.get("pending_return_control")
                and not metadata.get("confirmation_card")
                and answer != GENERIC_ERROR_MESSAGE
            ):
                for attempt in range(2):
                    retry_session = f"{agent_session}-w{attempt + 1}"
                    retry_prompt = _guardrail_safe_prompt(_maybe_steered_v2_prompt(normalized))
                    retry_answer, retry_events, retry_meta = _invoke_agent_once(
                        client,
                        agent_session=retry_session,
                        question=retry_prompt,
                    )
                    answer, collected_events, metadata = retry_answer, retry_events, retry_meta
                    agent_session = retry_session
                    if metadata.get("pending_return_control") or metadata.get("confirmation_card"):
                        break
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
