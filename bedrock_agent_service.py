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

WRITE_CONFIRM_TOOLS = frozenset(
    {
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
    }
)
ALLOWED_PUBLIC_TOOLS = frozenset(
    {
        "PlanMatchTactics",
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
        "GenerateCurrentLineupBoard",
    }
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


def is_enabled() -> bool:
    return AGENT_ENABLED and bool(AGENT_ID) and bool(AGENT_ALIAS_ID)


def disabled_response() -> dict[str, Any]:
    if not AGENT_ENABLED:
        return {"enabled": False, "message": DISABLED_MESSAGE, "refused": True}
    return {"enabled": False, "message": MISSING_CONFIG_MESSAGE, "refused": True}


def _sanitize_text(value: str) -> str:
    text = _ARN_PATTERN.sub("[redacted-resource]", value)
    text = re.sub(r"s3://[^\s]+", "[redacted-storage]", text, flags=re.I)
    return _ACCOUNT_PATTERN.sub("[redacted-account]", text)


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


def _extract_confirmation_card(events: list[dict], answer: str) -> dict[str, Any] | None:
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
        card: dict[str, Any] = {
            "function": fn,
            "parameters": params,
            "state": "pending",
        }
        if fn == "SubmitPlayerSelectionToManagement":
            card["title"] = "Submit recommendation to management"
            card["action_label"] = (
                "Submit recommendation to management and reserve budget"
            )
        elif fn == "FinalizeCurrentLineup":
            card["title"] = "Save proposed lineup for head-coach review"
            card["action_label"] = "Save proposed lineup for head-coach review"
        return card
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
    if "candidate" in fields or "formation" in fields:
        fn = (
            "FinalizeCurrentLineup"
            if "formation" in fields or "players" in fields
            else "SubmitPlayerSelectionToManagement"
        )
        card: dict[str, Any] = {
            "function": fn,
            "parameters": fields,
            "state": "pending",
        }
        if fn == "SubmitPlayerSelectionToManagement":
            card["title"] = "Submit recommendation to management"
            card["action_label"] = (
                "Submit recommendation to management and reserve budget"
            )
        else:
            card["title"] = "Save proposed lineup for head-coach review"
            card["action_label"] = "Save proposed lineup for head-coach review"
        return card
    return {
        "function": "unknown",
        "parameters": fields,
        "state": "pending",
        "title": "Action requires confirmation",
        "action_label": "Confirm this write action",
    }


def _extract_metadata(events: list[dict], answer: str) -> dict[str, Any]:
    tools: list[str] = []
    documents: list[str] = []
    warnings: list[str] = []
    lineup_route = None
    remaining_budget = None
    guardrail_intervened = False

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
            if payload.get("formation"):
                pass
        guard_trace = event.get("trace", {}).get("trace", {}).get("guardrailTrace")
        if guard_trace and guard_trace.get("action") == "INTERVENED":
            guardrail_intervened = True

    route_match = _LINEUP_ROUTE_PATTERN.search(answer)
    if route_match:
        lineup_route = route_match.group(0)
    budget_match = _REMAINING_BUDGET_PATTERN.search(answer)
    if budget_match and remaining_budget is None:
        remaining_budget = int(budget_match.group(1).replace(",", ""))

    confirmation_card = _extract_confirmation_card(events, answer)
    if confirmation_card and "confirmation_or_reprompt" not in warnings:
        warnings.append("confirmation_or_reprompt")

    return {
        "documents_used": documents[:8],
        "tools_executed": tools[:8],
        "lineup_image_route": lineup_route,
        "remaining_budget_eur": remaining_budget,
        "missing_information": None,
        "warnings": warnings[:4],
        "confirmation_card": confirmation_card,
        "guardrail_intervened": guardrail_intervened,
        "coach_brief": bool(_COACH_BRIEF_PREFIX.search(answer or "")),
    }


def invoke_agent(question: str, session_id: str | None = None) -> dict[str, Any]:
    if not is_enabled():
        return disabled_response()

    agent_session = session_id or f"advisor-{uuid.uuid4().hex}"
    collected_events: list[dict] = []
    try:
        client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=agent_session,
            inputText=question,
            enableTrace=True,
        )
        answer_parts: list[str] = []
        for event in response.get("completion", []):
            collected_events.append(event)
            if "chunk" in event and "bytes" in event["chunk"]:
                answer_parts.append(
                    event["chunk"]["bytes"].decode("utf-8", errors="replace")
                )
        answer = _sanitize_text("".join(answer_parts).strip()) or GENERIC_ERROR_MESSAGE
        metadata = _extract_metadata(collected_events, answer)
        refused = GUARDRAIL_BLOCK_MESSAGE.lower() in answer.lower()
        if metadata.get("guardrail_intervened") and not answer.strip():
            answer = GUARDRAIL_BLOCK_MESSAGE
            refused = True
        return {
            "enabled": True,
            "session_id": agent_session,
            "answer": answer,
            "refused": refused,
            "generation_mode": "bedrock_agent",
            "metadata": metadata,
        }
    except Exception:
        return {
            "enabled": True,
            "session_id": agent_session,
            "answer": GENERIC_ERROR_MESSAGE,
            "refused": True,
            "generation_mode": "bedrock_agent",
            "reason": "agent_error",
            "metadata": {},
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
    return {
        "answer": result.get("answer") or GENERIC_ERROR_MESSAGE,
        "refused": bool(result.get("refused")),
        "reason": result.get("reason"),
        "generation_mode": "bedrock_agent",
        "context": context,
        "main_source": main_source,
        "bedrock_session_id": result.get("session_id"),
        "agent_metadata": metadata,
    }
