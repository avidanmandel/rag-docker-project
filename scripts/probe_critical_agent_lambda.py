#!/usr/bin/env python3
import json
import uuid

import boto3

REGION = "us-east-1"
AGENT_ID = "3YMQVGTYSG"
STAGING_ALIAS = "T6N3TXAMCJ"
LAMBDA_TARGET = "ScoutMatchSubmitPlayerSelectionAvidan:scoutmatch-v2-staging"


def probe_lambda() -> None:
    lam = boto3.client("lambda", region_name=REGION)
    event = {
        "function": "SubmitCriticalDecisionAndSendEmail",
        "parameters": [
            {"name": "candidate_name", "value": "Ron Ben Ari"},
            {"name": "salary_eur", "value": "43000"},
            {"name": "target_role", "value": "Right-back"},
        ],
    }
    resp = lam.invoke(
        FunctionName=LAMBDA_TARGET,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode(),
    )
    raw = json.loads(resp["Payload"].read())
    print("lambda_status", resp.get("StatusCode"), "function_error", resp.get("FunctionError"))
    print(json.dumps(raw, indent=2)[:1500])


def probe_agent(prompt: str) -> bool:
    client = boto3.client("bedrock-agent-runtime", region_name=REGION)
    session_id = f"probe-{uuid.uuid4().hex[:10]}"
    resp = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=STAGING_ALIAS,
        sessionId=session_id,
        inputText=prompt,
        enableTrace=False,
    )
    parts = []
    return_control = False
    for event in resp.get("completion", []):
        if "chunk" in event:
            parts.append(event["chunk"]["bytes"].decode("utf-8", errors="replace"))
        if "returnControl" in event:
            return_control = True
    print("return_control", return_control, "answer:", "".join(parts)[:120].replace("\n", " "))
    return return_control


if __name__ == "__main__":
    mission = (
        "Invoke CreateAndReviewScoutingMission with candidate_name Ron Ben Ari "
        "and mission_mode CREATE_MISSION."
    )
    critical = (
        "Invoke SubmitCriticalDecisionAndSendEmail with candidate_name Ron Ben Ari, "
        "salary_eur 43000, and target_role Right-back."
    )
    for label, prompt in (("mission", mission), ("critical", critical)):
        ok = sum(probe_agent(prompt) for _ in range(5))
        print(label, "success", ok, "/ 5")
        print("---")
