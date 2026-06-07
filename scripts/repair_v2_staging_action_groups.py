#!/usr/bin/env python3
"""Disable legacy Action Groups on DRAFT and republish staging alias only."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
AGENT_ID = "3YMQVGTYSG"
STAGING_ALIAS_ID = "T6N3TXAMCJ"
PRODUCTION_ALIAS_ID = "MFWBSFNIDL"
STAGING_ALIAS_NAME = "scoutmatch-business-workflow-v2-staging"
REGION = "us-east-1"

V2_GROUPS = {
    "ScoutMatchCriticalDecisionActionsAvidan",
    "ScoutMatchTransferOutActionsAvidan",
    "ScoutMatchScoutingMissionActionsAvidan",
    "ScoutMatchSquadBoardActionsAvidan",
}

LEGACY_TO_DISABLE = {
    "ScoutMatchTacticsActionsAvidan",
    "ScoutMatchSelectionAgAvidan",
    "ScoutMatchLineupActionsAvidan",
    "ScoutMatchLineupBoardActionsAvidan",
}


def main() -> int:
    agent = boto3.client("bedrock-agent", region_name=REGION)
    prod_before = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version = str((prod_before.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))

    summaries = agent.list_agent_action_groups(agentId=AGENT_ID, agentVersion="DRAFT").get(
        "actionGroupSummaries", []
    )
    disabled = []
    for summary in summaries:
        name = summary.get("actionGroupName", "")
        if name not in LEGACY_TO_DISABLE:
            continue
        if summary.get("actionGroupState") == "DISABLED":
            continue
        detail = agent.get_agent_action_group(
            agentId=AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
        )["agentActionGroup"]
        agent.update_agent_action_group(
            agentId=AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
            actionGroupName=name,
            actionGroupState="DISABLED",
            actionGroupExecutor=detail.get("actionGroupExecutor", {}),
            functionSchema=detail.get("functionSchema", {}),
            description=detail.get("description", name),
        )
        disabled.append(name)

    agent.prepare_agent(agentId=AGENT_ID)
    deadline = time.time() + 180
    while time.time() < deadline:
        status = agent.get_agent(agentId=AGENT_ID)["agent"].get("agentStatus", "")
        if status == "PREPARED":
            break
        if status == "FAILED":
            raise RuntimeError("Agent prepare failed")
        time.sleep(6)

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
        detail = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=STAGING_ALIAS_ID)["agentAlias"]
        if detail.get("agentAliasStatus") == "PREPARED" and detail.get("routingConfiguration"):
            staging_version = str(detail["routingConfiguration"][0].get("agentVersion", ""))
            break
        time.sleep(6)

    enabled = {
        s.get("actionGroupName")
        for s in agent.list_agent_action_groups(agentId=AGENT_ID, agentVersion=staging_version).get(
            "actionGroupSummaries", []
        )
        if s.get("actionGroupState") == "ENABLED"
    }
    prod_after = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version_after = str((prod_after.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))

    report = {
        "disabled_on_draft": disabled,
        "staging_version": staging_version,
        "staging_enabled_groups": sorted(enabled),
        "staging_exactly_four_v2": enabled == V2_GROUPS,
        "production_version_before": prod_version,
        "production_version_after": prod_version_after,
        "production_unchanged": prod_version == prod_version_after,
    }
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state["agent_staging_alias_id"] = STAGING_ALIAS_ID
    state["agent_staging_version"] = staging_version
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["staging_exactly_four_v2"] and report["production_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
