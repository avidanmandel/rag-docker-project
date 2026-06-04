"""
Optional ScoutMatch Bedrock Flow integration (disabled by default).

Does not modify the production /api/chat or session RAG flow.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import boto3

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env.agent", override=False)
except Exception:
    pass

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
FLOW_ENABLED = os.getenv("SCOUTMATCH_FLOW_EXTENSION_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
FLOW_ID = (os.getenv("SCOUTMATCH_FLOW_ID") or "").strip()
FLOW_ALIAS_ID = (os.getenv("SCOUTMATCH_FLOW_ALIAS_ID") or "").strip()

DISABLED_MESSAGE = (
    "ScoutMatch Bedrock Flow extension is disabled. "
    "Set SCOUTMATCH_FLOW_EXTENSION_ENABLED=true and configure flow IDs in .env.agent (local only)."
)
MISSING_CONFIG_MESSAGE = (
    "ScoutMatch Flow extension is enabled but SCOUTMATCH_FLOW_ID or "
    "SCOUTMATCH_FLOW_ALIAS_ID is not configured."
)
GENERIC_ERROR_MESSAGE = "The recruitment flow could not complete this request."


def is_enabled() -> bool:
    return FLOW_ENABLED and bool(FLOW_ID) and bool(FLOW_ALIAS_ID)


def disabled_response() -> dict:
    if not FLOW_ENABLED:
        return {"enabled": False, "message": DISABLED_MESSAGE, "refused": True}
    return {"enabled": False, "message": MISSING_CONFIG_MESSAGE, "refused": True}


def invoke_flow(question: str, session_id: str | None = None) -> dict:
    """Invoke the configured Bedrock Flow alias safely."""
    if not FLOW_ENABLED:
        return disabled_response()
    if not FLOW_ID or not FLOW_ALIAS_ID:
        return disabled_response()

    flow_session = session_id or f"flow-{uuid.uuid4().hex}"
    try:
        client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)
        response = client.invoke_flow(
            flowIdentifier=FLOW_ID,
            flowAliasIdentifier=FLOW_ALIAS_ID,
            inputs=[
                {
                    "nodeName": "ScoutMatchFlowInput",
                    "nodeOutputName": "document",
                    "content": {"document": question},
                }
            ],
        )
        answer_parts: list[str] = []
        for event in response.get("responseStream", []):
            if "flowOutputEvent" in event:
                content = event["flowOutputEvent"].get("content", {})
                doc = content.get("document", "")
                if isinstance(doc, str):
                    answer_parts.append(doc)
                elif doc:
                    answer_parts.append(str(doc))
        answer = "".join(answer_parts).strip() or "No response returned from the flow."
        return {
            "enabled": True,
            "session_id": flow_session,
            "answer": answer,
            "refused": False,
            "generation_mode": "bedrock_flow",
        }
    except Exception:
        return {
            "enabled": True,
            "session_id": flow_session,
            "answer": GENERIC_ERROR_MESSAGE,
            "refused": True,
            "generation_mode": "bedrock_flow",
            "reason": "flow_error",
        }
