#!/usr/bin/env python3
"""Invoke the ScoutMatch recruitment flow alias."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", help="Flow input document text")
    args = parser.parse_args()

    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    flow_id = state.get("flow_id") or ""
    alias_id = state.get("flow_alias_id") or ""
    if not flow_id or not alias_id:
        print("Missing flow_id or flow_alias_id in local state. Run deploy --apply first.")
        return 2

    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    resp = client.invoke_flow(
        flowIdentifier=flow_id,
        flowAliasIdentifier=alias_id,
        inputs=[
            {
                "nodeName": "ScoutMatchFlowInput",
                "nodeOutputName": "document",
                "content": {"document": args.prompt},
            }
        ],
    )
    for event in resp.get("responseStream", []):
        if "flowOutputEvent" in event:
            doc = event["flowOutputEvent"]["content"].get("document", "")
            print(doc if isinstance(doc, str) else json.dumps(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
