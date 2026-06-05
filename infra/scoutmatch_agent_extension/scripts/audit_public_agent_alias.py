#!/usr/bin/env python3
"""Read-only audit of public Recruitment Advisor Agent alias vs draft."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
AGENT_NAME = "scoutmatch-recruitment-agent-user5-avidan"
ALIAS_NAME = "scoutmatch-demo-stable-v2"
FINAL_GROUPS = {
    "ScoutMatchTacticsActionsAvidan",
    "ScoutMatchSelectionAgAvidan",
    "ScoutMatchLineupActionsAvidan",
    "ScoutMatchLineupBoardActionsAvidan",
}
FINAL_FUNCTIONS = {
    "PlanMatchTactics",
    "SubmitPlayerSelectionToManagement",
    "FinalizeCurrentLineup",
    "GenerateCurrentLineupBoard",
}
LEGACY_FUNCTIONS = {
    "CalculateBudgetImpact",
    "EvaluateRightBackFit",
    "EvaluateBelowStrikerFit",
    "EvaluateForwardFit",
    "AddCandidateToShortlist",
    "StartCandidateReviewWorkflow",
    "CreateRecruitmentBrief",
    "UpdateSquadPlanningContext",
}


def _load_ids() -> tuple[str, str]:
    agent_id = alias_id = ""
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        agent_id = str(state.get("agent_id") or "")
        alias_id = str(state.get("agent_alias_id") or "")
    env_agent = ROOT / ".env.agent"
    if env_agent.exists():
        for line in env_agent.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "SCOUTMATCH_AGENT_ID" and not agent_id:
                agent_id = v
            if k == "SCOUTMATCH_AGENT_ALIAS_ID" and not alias_id:
                alias_id = v
    if not agent_id or not alias_id:
        raise SystemExit("Missing agent or alias id in state/.env.agent")
    return agent_id, alias_id


def _group_functions(client, agent_id: str, version: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    groups = client.list_agent_action_groups(agentId=agent_id, agentVersion=version).get(
        "actionGroupSummaries", []
    )
    for summary in groups:
        name = summary.get("actionGroupName", "")
        state = summary.get("actionGroupState", "ENABLED")
        if state != "ENABLED":
            continue
        detail = client.get_agent_action_group(
            agentId=agent_id,
            agentVersion=version,
            actionGroupId=summary["actionGroupId"],
        )["agentActionGroup"]
        fns = [fn.get("name", "") for fn in detail.get("functionSchema", {}).get("functions", [])]
        out[name] = fns
    return out


def _flatten_functions(groups: dict[str, list[str]]) -> set[str]:
    names: set[str] = set()
    for fns in groups.values():
        names.update(fns)
    return names


def _confirmation_flags(client, agent_id: str, version: str) -> dict[str, str]:
    flags: dict[str, str] = {}
    groups = client.list_agent_action_groups(agentId=agent_id, agentVersion=version).get(
        "actionGroupSummaries", []
    )
    for summary in groups:
        if summary.get("actionGroupState") != "ENABLED":
            continue
        detail = client.get_agent_action_group(
            agentId=agent_id,
            agentVersion=version,
            actionGroupId=summary["actionGroupId"],
        )["agentActionGroup"]
        for fn in detail.get("functionSchema", {}).get("functions", []):
            flags[fn.get("name", "")] = fn.get("requireConfirmation", "DISABLED")
    return flags


def _redact(obj: dict) -> dict:
    text = json.dumps(obj)
    text = re.sub(r"\b[0-9]{12}\b", "[ACCOUNT]", text)
    text = re.sub(r"arn:aws:[^\"]+", "[REDACTED_ARN]", text)
    return json.loads(text)


def main() -> int:
    agent_id, alias_id = _load_ids()
    client = boto3.client("bedrock-agent", region_name=REGION)
    alias = client.get_agent_alias(agentId=agent_id, agentAliasId=alias_id)["agentAlias"]
    alias_version = str(
        alias.get("routingConfiguration", [{}])[0].get("agentVersion", "")
    )
    draft_groups = _group_functions(client, agent_id, "DRAFT")
    alias_groups = _group_functions(client, agent_id, alias_version) if alias_version.isdigit() else {}
    draft_fn = _flatten_functions(draft_groups)
    alias_fn = _flatten_functions(alias_groups)
    draft_confirm = _confirmation_flags(client, agent_id, "DRAFT")
    alias_confirm = (
        _confirmation_flags(client, agent_id, alias_version) if alias_version.isdigit() else {}
    )
    kb = client.list_agent_knowledge_bases(agentId=agent_id, agentVersion=alias_version or "DRAFT")
    kb_enabled = any(
        (x.get("knowledgeBaseState") or "").upper() == "ENABLED"
        for x in kb.get("agentKnowledgeBaseSummaries", [])
    )
    agent_detail = client.get_agent(agentId=agent_id)["agent"]
    guard = agent_detail.get("guardrailConfiguration") or {}
    stale = bool(
        alias_version.isdigit()
        and (
            set(alias_groups) != FINAL_GROUPS
            or bool(alias_fn & LEGACY_FUNCTIONS)
            or not FINAL_FUNCTIONS.issubset(alias_fn)
        )
    )
    report = {
        "agent_name": AGENT_NAME,
        "alias_name": alias.get("agentAliasName", ALIAS_NAME),
        "alias_routes_to_version": alias_version,
        "alias_stale_vs_four_tool": stale,
        "draft_enabled_action_groups": sorted(draft_groups),
        "alias_enabled_action_groups": sorted(alias_groups),
        "draft_function_names": sorted(draft_fn),
        "alias_function_names": sorted(alias_fn),
        "legacy_functions_on_alias": sorted(alias_fn & LEGACY_FUNCTIONS),
        "draft_missing_final_functions": sorted(FINAL_FUNCTIONS - draft_fn),
        "alias_missing_final_functions": sorted(FINAL_FUNCTIONS - alias_fn),
        "selection_confirmation_draft": draft_confirm.get("SubmitPlayerSelectionToManagement"),
        "selection_confirmation_alias": alias_confirm.get("SubmitPlayerSelectionToManagement"),
        "lineup_confirmation_draft": draft_confirm.get("FinalizeCurrentLineup"),
        "lineup_confirmation_alias": alias_confirm.get("FinalizeCurrentLineup"),
        "knowledge_base_enabled": kb_enabled,
        "guardrail_attached_on_agent": bool(guard.get("guardrailIdentifier")),
        "root_cause": (
            "Public alias routes to a prepared agent version that still exposes legacy helper "
            "Action Groups/schemas (for example CalculateBudgetImpact / EvaluateRightBackFit), "
            "not the four-tool draft configuration."
            if stale
            else "Public alias matches four-tool draft configuration."
        ),
    }
    print(json.dumps(_redact(report), indent=2))
    return 2 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
