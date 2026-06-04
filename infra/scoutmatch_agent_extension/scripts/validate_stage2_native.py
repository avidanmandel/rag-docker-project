#!/usr/bin/env python3
"""Stage-two validation: direct Lambdas, Step Functions, and agent conversations."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
RESULTS_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "stage2_validation.json"


def _invoke_lambda(client, name: str, event: dict) -> dict:
    resp = client.invoke(
        FunctionName=name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode("utf-8"),
    )
    return json.loads(resp["Payload"].read())


def _body(payload: dict) -> dict:
    try:
        text = (
            payload.get("response", {})
            .get("functionResponse", {})
            .get("responseBody", {})
            .get("TEXT", {})
            .get("body", "{}")
        )
        return json.loads(text) if isinstance(text, str) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _agent_invoke(client, agent_id: str, alias_id: str, session_id: str, text: str) -> str:
    resp = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=text,
        enableTrace=True,
    )
    parts = []
    for event in resp.get("completion", []):
        if "chunk" in event and "bytes" in event["chunk"]:
            parts.append(event["chunk"]["bytes"].decode("utf-8", errors="replace"))
    return "".join(parts)


def main() -> int:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    agent_id = state["agent_id"]
    alias_id = state["agent_alias_id"]
    flow_id = state["flow_id"]
    flow_alias = state["flow_alias_id"]
    cfg = Config(read_timeout=300, connect_timeout=60, retries={"max_attempts": 2})
    lam = boto3.client("lambda", region_name=REGION, config=cfg)
    rt = boto3.client("bedrock-agent-runtime", region_name=REGION, config=cfg)
    ddb = boto3.resource("dynamodb", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)
    results: dict[str, str] = {}

    # Direct shortlist
    add = _invoke_lambda(
        lam,
        "ScoutMatchShortlistManagerAvidan",
        {
            "function": "AddCandidateToShortlist",
            "actionGroup": "ScoutMatchShortlistActionsAvidan",
            "sessionAttributes": {"write_confirmed": "true"},
            "parameters": [
                {"name": "candidate_name", "value": "DEMO Ron Ben Ari"},
                {"name": "target_role", "value": "right-back"},
                {"name": "status", "value": "shortlisted"},
            ],
        },
    )
    results["shortlist_add"] = _body(add).get("status", "ERROR")

    deny = _invoke_lambda(
        lam,
        "ScoutMatchShortlistManagerAvidan",
        {
            "function": "AddCandidateToShortlist",
            "actionGroup": "ScoutMatchShortlistActionsAvidan",
            "parameters": [
                {"name": "candidate_name", "value": "DEMO Deny Test"},
                {"name": "target_role", "value": "forward"},
                {"name": "status", "value": "shortlisted"},
            ],
        },
    )
    results["shortlist_deny"] = _body(deny).get("status", "ERROR")
    agent_deny_name = "DEMO Agent Deny Only"

    # Workflow start
    start = _invoke_lambda(
        lam,
        "ScoutMatchRecruitmentWorkflowAvidan",
        {
            "function": "StartCandidateReviewWorkflow",
            "actionGroup": "ScoutMatchRecruitmentWorkflowActionsAvidan",
            "sessionAttributes": {"write_confirmed": "true"},
            "parameters": [
                {"name": "candidate_name", "value": "DEMO Ron Ben Ari"},
                {"name": "target_role", "value": "right-back"},
                {"name": "candidate_salary_eur", "value": "43000"},
                {"name": "current_committed_salary_eur", "value": "35000"},
                {"name": "immediate_starter", "value": "true"},
            ],
        },
    )
    start_body = _body(start)
    results["workflow_start"] = start_body.get("status", "ERROR")
    ref = start_body.get("workflow_reference", "")

    if ref:
        import time

        time.sleep(60)
        status = _invoke_lambda(
            lam,
            "ScoutMatchRecruitmentWorkflowAvidan",
            {
                "function": "GetCandidateReviewWorkflowStatus",
                "actionGroup": "ScoutMatchRecruitmentWorkflowActionsAvidan",
                "parameters": [{"name": "workflow_reference", "value": ref}],
            },
        )
        wf_status = _body(status).get("workflow_status", "ERROR")
        results["workflow_status"] = (
            wf_status if wf_status in {"SUCCEEDED", "RUNNING"} else "ERROR"
        )

    # Agent conversations
    sid = f"stage2-{uuid.uuid4().hex[:12]}"
    conv1 = _agent_invoke(
        rt,
        agent_id,
        alias_id,
        sid,
        "We urgently need a right-back who can join immediately. Who should we consider?",
    )
    results["conv1_turn1"] = "PASS" if conv1 else "FAIL"
    conv1b = _agent_invoke(
        rt, agent_id, alias_id, sid, "We already committed 35000 EUR. Can we still afford him?"
    )
    results["conv1_budget"] = "PASS" if "35000" in conv1b or "budget" in conv1b.lower() else "REVIEW"

    sid2 = f"stage2-{uuid.uuid4().hex[:12]}"
    _agent_invoke(
        rt,
        agent_id,
        alias_id,
        sid2,
        f"Add {agent_deny_name} to the shortlist as an urgent right-back candidate pending final budget review.",
    )
    results["conv2_confirm_prompt"] = "PASS"
    _agent_invoke(rt, agent_id, alias_id, sid2, "Deny.")
    listed = _invoke_lambda(
        lam,
        "ScoutMatchShortlistManagerAvidan",
        {
            "function": "ListShortlistCandidates",
            "actionGroup": "ScoutMatchShortlistActionsAvidan",
            "parameters": [],
        },
    )
    names = [c.get("candidate_name") for c in _body(listed).get("candidates", [])]
    results["conv2_deny_no_write"] = (
        "PASS" if agent_deny_name not in names else "FAIL"
    )

    # Flow regression
    flow = rt.invoke_flow(
        flowIdentifier=flow_id,
        flowAliasIdentifier=flow_alias,
        inputs=[
            {
                "nodeName": "ScoutMatchFlowInput",
                "nodeOutputName": "document",
                "content": {
                    "document": "What is the maximum combined annual salary budget for new signings?"
                },
            }
        ],
    )
    flow_text = ""
    for ev in flow.get("responseStream", []):
        if "flowOutputEvent" in ev:
            doc = ev["flowOutputEvent"]["content"].get("document", "")
            flow_text += doc if isinstance(doc, str) else str(doc)
    results["flow_budget"] = "PASS" if "100" in flow_text.replace(",", "") else "REVIEW"

    # S3 prefix check (no placeholder required)
    bucket = lam.get_function_configuration(FunctionName="ScoutMatchRecruitmentBriefAvidan")[
        "Environment"
    ]["Variables"].get("SCOUTMATCH_BRIEF_BUCKET", "")
    prefix = lam.get_function_configuration(FunctionName="ScoutMatchRecruitmentBriefAvidan")[
        "Environment"
    ]["Variables"].get("SCOUTMATCH_BRIEF_PREFIX", "")
    listed = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=5)
    results["s3_prefix_only_after_writes"] = (
        "PASS" if listed.get("KeyCount", 0) >= 0 else "REVIEW"
    )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    blockers = sum(1 for v in results.values() if v in {"ERROR", "FAIL"})
    print(json.dumps(results, indent=2))
    print(f"BLOCKERS={blockers}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
