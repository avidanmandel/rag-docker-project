#!/usr/bin/env python3
"""Invoke the ScoutMatch recruitment agent alias with a single prompt."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", help="User prompt text")
    parser.add_argument("--session-id", default="")
    args = parser.parse_args()

    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    agent_id = state.get("agent_id") or ""
    alias_id = state.get("agent_alias_id") or ""
    if not agent_id or not alias_id:
        print("Missing agent_id or agent_alias_id in local state. Run deploy --apply first.")
        return 2

    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    session_id = args.session_id or f"scoutmatch-{uuid.uuid4().hex[:16]}"
    response = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=args.prompt,
    )
    text_parts = []
    for event in response.get("completion", []):
        if "chunk" in event and "bytes" in event["chunk"]:
            text_parts.append(event["chunk"]["bytes"].decode("utf-8", errors="replace"))
    print("".join(text_parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
