#!/usr/bin/env python3
"""Update staging Bedrock Agent instruction for immediate write-tool returnControl."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "infra" / "scoutmatch_agent_extension" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"))

from four_lambda_apply import AGENT_INSTRUCTION_V2  # noqa: E402

STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
AGENT_ID = "3YMQVGTYSG"
STAGING_ALIAS_ID = "T6N3TXAMCJ"
PRODUCTION_ALIAS_ID = "MFWBSFNIDL"
STAGING_ALIAS_NAME = "scoutmatch-business-workflow-v2-staging"
REGION = "us-east-1"


def _wait_prepared(agent, agent_id: str, *, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = agent.get_agent(agentId=agent_id)["agent"].get("agentStatus", "")
        if status == "PREPARED":
            return
        if status == "FAILED":
            raise RuntimeError("Agent prepare failed")
        time.sleep(6)
    raise TimeoutError("Timed out waiting for agent prepare")


def main() -> int:
    agent = boto3.client("bedrock-agent", region_name=REGION)
    prod_before = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version = str((prod_before.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))

    detail = agent.get_agent(agentId=AGENT_ID)["agent"]
    agent.update_agent(
        agentId=AGENT_ID,
        agentName=detail["agentName"],
        agentResourceRoleArn=detail["agentResourceRoleArn"],
        foundationModel=detail["foundationModel"],
        instruction=AGENT_INSTRUCTION_V2,
        idleSessionTTLInSeconds=int(detail.get("idleSessionTTLInSeconds") or 600),
    )
    agent.prepare_agent(agentId=AGENT_ID)
    _wait_prepared(agent, AGENT_ID)

    agent.update_agent_alias(
        agentId=AGENT_ID,
        agentAliasId=STAGING_ALIAS_ID,
        agentAliasName=STAGING_ALIAS_NAME,
        description="Business workflow v2 staging alias — do not use for public cutover",
        aliasInvocationState="ACCEPT_INVOCATIONS",
    )

    staging_version = ""
    deadline = time.time() + 240
    while time.time() < deadline:
        alias = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=STAGING_ALIAS_ID)["agentAlias"]
        if alias.get("agentAliasStatus") == "PREPARED" and alias.get("routingConfiguration"):
            staging_version = str(alias["routingConfiguration"][0].get("agentVersion", ""))
            break
        if alias.get("agentAliasStatus") == "FAILED":
            raise RuntimeError(f"Staging alias publish failed: {alias.get('failureReasons')}")
        time.sleep(6)

    prod_after = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version_after = str((prod_after.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))

    report = {
        "staging_alias_id": STAGING_ALIAS_ID,
        "staging_version": staging_version,
        "production_version_before": prod_version,
        "production_version_after": prod_version_after,
        "production_unchanged": prod_version == prod_version_after,
    }
    if STATE_PATH.is_file():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state["agent_staging_version"] = staging_version
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["production_unchanged"] and staging_version.isdigit() else 1


if __name__ == "__main__":
    raise SystemExit(main())
