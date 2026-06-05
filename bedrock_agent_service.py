"""
Optional ScoutMatch Bedrock Agent recruitment advisor (disabled by default).

Uses Amazon Bedrock Agent invoke only — no direct Lambda selection by the user.
"""

from __future__ import annotations

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

_ARN_PATTERN = re.compile(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:[0-9]{12}:[^\s]+", re.I)
_ACCOUNT_PATTERN = re.compile(r"\b[0-9]{12}\b")
_LINEUP_ROUTE_PATTERN = re.compile(r"/api/recruitment-advisor/lineups/[a-zA-Z0-9_-]+/image")
_REMAINING_BUDGET_PATTERN = re.compile(
    r"remaining(?:\s+available)?\s+budget[:\s]+([0-9][0-9,]*)\s*EUR",
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
    return _ACCOUNT_PATTERN.sub("[redacted-account]", text)


def _extract_metadata(events: list[dict]) -> dict[str, Any]:
    tools: list[str] = []
    documents: list[str] = []
    warnings: list[str] = []
    for event in events:
        if "trace" not in event:
            continue
        trace = event.get("trace") or {}
        orchestration = trace.get("trace", {}).get("orchestrationTrace") or {}
        invocation = orchestration.get("invocationInput") or {}
        if "actionGroupInvocationInput" in invocation:
            ag = invocation["actionGroupInvocationInput"]
            fn = ag.get("function") or ag.get("actionGroupName") or "tool"
            if fn not in tools:
                tools.append(str(fn))
        observation = orchestration.get("observation") or {}
        kb = observation.get("knowledgeBaseLookupOutput") or {}
        for ref in kb.get("retrievedReferences") or []:
            loc = ref.get("location", {}).get("s3Location", {}).get("uri", "")
            name = loc.rsplit("/", 1)[-1] if loc else ""
            if name and name not in documents:
                documents.append(name)
        if observation.get("repromptResponse"):
            warnings.append("confirmation_or_reprompt")
    lineup_route = None
    remaining_budget = None
    for event in events:
        if "trace" not in event:
            continue
        trace = event.get("trace") or {}
        observation = trace.get("trace", {}).get("orchestrationTrace", {}).get("observation") or {}
        action_response = observation.get("actionGroupInvocationOutput") or {}
        text = (
            action_response.get("text", "")
            or str(action_response.get("actionGroupInvocationOutput", ""))
        )
        if "image_route" in text and "/api/recruitment-advisor/lineups/" in text:
            import json

            try:
                payload = json.loads(text) if text.strip().startswith("{") else {}
            except json.JSONDecodeError:
                payload = {}
            if not payload and "image_route" in text:
                start = text.find("/api/recruitment-advisor/lineups/")
                if start >= 0:
                    end = text.find('"', start)
                    lineup_route = text[start:end] if end > start else text[start:].split()[0]
            else:
                lineup_route = payload.get("image_route")
            if payload.get("remaining_budget_eur") is not None:
                remaining_budget = payload.get("remaining_budget_eur")
    return {
        "documents_used": documents[:8],
        "tools_executed": tools[:8],
        "workflow_status": next((t for t in tools if "Workflow" in t), None),
        "shortlist_action": next((t for t in tools if "Shortlist" in t), None),
        "recruitment_brief_created": any("Brief" in t for t in tools),
        "lineup_image_route": lineup_route,
        "remaining_budget_eur": remaining_budget,
        "missing_information": None,
        "warnings": warnings[:4],
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
        metadata = _extract_metadata(collected_events)
        route_match = _LINEUP_ROUTE_PATTERN.search(answer)
        if route_match:
            metadata["lineup_image_route"] = route_match.group(0)
        budget_match = _REMAINING_BUDGET_PATTERN.search(answer)
        if budget_match and metadata.get("remaining_budget_eur") is None:
            metadata["remaining_budget_eur"] = int(budget_match.group(1).replace(",", ""))
        return {
            "enabled": True,
            "session_id": agent_session,
            "answer": answer,
            "refused": False,
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
