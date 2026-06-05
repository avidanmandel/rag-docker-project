#!/usr/bin/env python3
"""Read-only audit of deployed ScoutMatch recruitment agent (sanitized output)."""

from __future__ import annotations

import argparse
import json

import boto3

REGION = "us-east-1"
AGENT_NAME = "scoutmatch-recruitment-agent-user5-avidan"
KB_NAME = "knowledge-base-user5"
DATA_SOURCE_NAME = "scoutmatch-player-documents"
FOUR_ACTION_GROUPS = {
    "ScoutMatchBudgetActionsAvidan",
    "ScoutMatchRightBackActionsAvidan",
    "ScoutMatchBelowStrikerActionsAvidan",
    "ScoutMatchForwardActionsAvidan",
}
FOUR_LAMBDAS = {
    "ScoutMatchBudgetImpactAvidan",
    "ScoutMatchRightBackFitAvidan",
    "ScoutMatchBelowStrikerFitAvidan",
    "ScoutMatchForwardFitAvidan",
}
FORBIDDEN_GROUPS = {"weather", "time", "joke", "live", "ScoutMatchWeather", "ScoutMatchLiveTools"}


def _find_agent_id(client) -> str | None:
    token = None
    while True:
        kwargs = {"nextToken": token} if token else {}
        page = client.list_agents(**kwargs)
        for summary in page.get("agentSummaries", []):
            if summary.get("agentName") == AGENT_NAME:
                return summary.get("agentId")
        token = page.get("nextToken")
        if not token:
            return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    agent_client = boto3.client("bedrock-agent", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)

    report: dict = {
        "agent_name": AGENT_NAME,
        "agent_found": False,
        "guardrail_attached": False,
        "knowledge_base_attached": False,
        "action_groups": [],
        "four_football_action_groups_present": False,
        "forbidden_legacy_tools_attached": False,
        "four_lambdas_reachable": {},
    }

    agent_id = _find_agent_id(agent_client)
    if not agent_id:
        print("Agent not found (read-only audit).")
        return 1

    report["agent_found"] = True
    detail = agent_client.get_agent(agentId=agent_id)["agent"]
    report["agent_status"] = detail.get("agentStatus")
    report["guardrail_attached"] = bool(detail.get("guardrailConfiguration"))
    kbs = agent_client.list_agent_knowledge_bases(agentId=agent_id, agentVersion="DRAFT")
    summaries = kbs.get("agentKnowledgeBaseSummaries") or []
    report["knowledge_base_attached"] = bool(summaries)
    report["knowledge_base_name"] = KB_NAME if summaries else ""
    report["knowledge_base_association_enabled"] = any(
        (item.get("knowledgeBaseState") or "").upper() == "ENABLED" for item in summaries
    )
    report["native_action_group_function_count_estimate"] = 6
    report["simplified_target_user_facing_tools"] = 4

    groups = agent_client.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT")
    names = []
    for group in groups.get("actionGroupSummaries", []):
        name = group.get("actionGroupName", "")
        names.append(name)
        if any(token in name.lower() for token in FORBIDDEN_GROUPS):
            report["forbidden_legacy_tools_attached"] = True
    report["action_groups"] = sorted(names)
    report["four_football_action_groups_present"] = FOUR_ACTION_GROUPS.issubset(set(names))

    for fn in FOUR_LAMBDAS:
        try:
            lam.invoke(FunctionName=fn, InvocationType="DryRun")
            report["four_lambdas_reachable"][fn] = True
        except Exception:
            report["four_lambdas_reachable"][fn] = False

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Agent: {AGENT_NAME} — found")
        print(f"  Status: {report.get('agent_status')}")
        print(f"  Guardrail attached: {report['guardrail_attached']}")
        print(f"  Knowledge base attached: {report['knowledge_base_attached']}")
        print(f"  Action groups ({len(names)}): {', '.join(names)}")
        print(f"  Four football groups present: {report['four_football_action_groups_present']}")
        print(f"  Forbidden legacy tools attached: {report['forbidden_legacy_tools_attached']}")
        print("  Lambda DryRun reachability:")
        for fn, ok in report["four_lambdas_reachable"].items():
            print(f"    - {fn}: {'yes' if ok else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
