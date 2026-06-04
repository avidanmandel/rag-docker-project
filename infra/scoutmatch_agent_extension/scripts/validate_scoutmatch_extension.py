#!/usr/bin/env python3
"""Validate ScoutMatch extension Lambdas, Agent alias, and Flow alias."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"

PROMPTS = [
    (
        "kb_budget",
        "What is the maximum combined annual salary budget for new signings?",
        "100000",
    ),
    (
        "budget_pass",
        "Can ScoutMatch sign a player named Example Player with an annual salary of 58000 EUR if 35000 EUR is already committed?",
        "PASS",
    ),
    (
        "budget_fail",
        "Can ScoutMatch sign a player named Example Player with an annual salary of 70000 EUR if 50000 EUR is already committed?",
        "FAIL",
    ),
]


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", action="store_true", help="Invoke agent alias prompts")
    parser.add_argument("--flow", action="store_true", help="Invoke flow alias")
    parser.add_argument("--lambda-only", action="store_true", help="Direct Lambda tests only")
    args = parser.parse_args()

    session = boto3.Session(region_name=REGION)
    lam = session.client("lambda")
    agent = session.client("bedrock-agent-runtime")
    state = _load_state()
    blockers = 0

    payload = {
        "parameters": [
            {"name": "candidate_name", "value": "Example Player"},
            {"name": "candidate_annual_salary_eur", "value": "58000"},
            {"name": "current_committed_salary_eur", "value": "35000"},
            {"name": "immediate_starter", "value": "false"},
        ],
        "actionGroup": "ScoutMatchBudgetActionsAvidan",
        "function": "CalculateBudgetImpact",
    }
    resp = lam.invoke(
        FunctionName="ScoutMatchBudgetImpactAvidan",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    body = json.loads(resp["Payload"].read())
    print("Lambda ScoutMatchBudgetImpactAvidan:", "ok" if "FunctionError" not in resp else body)

    if args.lambda_only:
        return 0

    agent_id = state.get("agent_id")
    alias_id = state.get("agent_alias_id")
    if args.agent and agent_id and alias_id:
        for code, text, expect in PROMPTS:
            try:
                out = agent.invoke_agent(
                    agentId=agent_id,
                    agentAliasId=alias_id,
                    sessionId=f"validate-{code}",
                    inputText=text,
                )
                chunks = []
                for event in out.get("completion", []):
                    if "chunk" in event and "bytes" in event["chunk"]:
                        chunks.append(event["chunk"]["bytes"].decode("utf-8", errors="replace"))
                answer = "".join(chunks)
                ok = expect.lower() in answer.lower()
                print(f"[{code}] expect~{expect}: {'PASS' if ok else 'REVIEW'}")
                if not ok:
                    blockers += 1
            except Exception as exc:
                print(f"[{code}] ERROR: {type(exc).__name__}")
                blockers += 1

    flow_id = state.get("flow_id")
    flow_alias_id = state.get("flow_alias_id")
    if args.flow and flow_id and flow_alias_id:
        try:
            resp = agent.invoke_flow(
                flowIdentifier=flow_id,
                flowAliasIdentifier=flow_alias_id,
                inputs=[
                    {
                        "nodeName": "ScoutMatchFlowInput",
                        "nodeOutputName": "document",
                        "content": {"document": "Summarize the winter transfer budget limit."},
                    }
                ],
            )
            print("Flow invocation: started")
            for event in resp.get("responseStream", []):
                if "flowOutputEvent" in event:
                    print("Flow output received")
        except Exception as exc:
            print(f"Flow invocation ERROR: {type(exc).__name__}")
            blockers += 1

    print(f"BLOCKERS: {blockers}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
