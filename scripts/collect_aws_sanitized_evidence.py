#!/usr/bin/env python3
"""Collect sanitized AWS text evidence (no secrets, no full ARNs in output)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
OUT = ROOT / "artifacts" / "evidence"
ARN_RE = re.compile(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:(.+)")


def _suffix(value: str) -> str:
    if not value:
        return ""
    if value.startswith("arn:aws:"):
        match = ARN_RE.match(value)
        return match.group(1) if match else "<redacted-arn>"
    return value


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, object] = {"region": REGION, "checks": {}}

    bedrock = boto3.client("bedrock", region_name=REGION)
    agent_rt = boto3.client("bedrock-agent", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)
    ddb = boto3.client("dynamodb", region_name=REGION)

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    agent_id = str(state.get("agent_id") or "")
    alias_id = str(state.get("agent_alias_id") or "")
    guardrail_id = str(state.get("guardrail_id") or "")
    guardrail_version = str(state.get("guardrail_version") or "")

    if agent_id:
        agent = agent_rt.get_agent(agentId=agent_id)["agent"]
        evidence["checks"]["agent_status"] = agent.get("agentStatus")
        evidence["checks"]["agent_name"] = agent.get("agentName")
        kbs = agent_rt.list_agent_knowledge_bases(agentId=agent_id, agentVersion="DRAFT").get(
            "agentKnowledgeBaseSummaries", []
        )
        evidence["checks"]["knowledge_base_associations"] = [
            {
                "description": kb.get("description", ""),
                "status": kb.get("knowledgeBaseState", ""),
                "kb_suffix": _suffix(kb.get("knowledgeBaseId", "")),
            }
            for kb in kbs
        ]
        groups = agent_rt.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT").get(
            "actionGroupSummaries", []
        )
        evidence["checks"]["action_group_count"] = len(groups)
        evidence["checks"]["action_group_names"] = sorted(g.get("actionGroupName", "") for g in groups)

    if alias_id and agent_id:
        alias = agent_rt.get_agent_alias(agentId=agent_id, agentAliasId=alias_id)["agentAlias"]
        evidence["checks"]["alias_name"] = alias.get("agentAliasName")
        evidence["checks"]["alias_status"] = alias.get("agentAliasStatus")
        evidence["checks"]["alias_routing_version"] = alias.get("routingConfiguration", [{}])[0].get(
            "agentVersion", ""
        )

    if guardrail_id:
        gr = bedrock.get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion=guardrail_version or "DRAFT")
        filters = (gr.get("contentPolicy") or gr.get("contentPolicyConfig") or {}).get("filters") or (
            gr.get("contentPolicyConfig", {}).get("filtersConfig") or []
        )
        evidence["checks"]["guardrail_suffix"] = _suffix(guardrail_id)
        evidence["checks"]["guardrail_version"] = guardrail_version or gr.get("version", "")
        evidence["checks"]["guardrail_filters"] = [
            {"type": f.get("type"), "input": f.get("inputStrength")} for f in filters
        ]

    final_lambdas = [
        "ScoutMatchPlanMatchTacticsAvidan",
        "ScoutMatchSubmitPlayerSelectionAvidan",
        "ScoutMatchFinalizeCurrentLineupAvidan",
        "ScoutMatchGenerateLineupBoardAvidan",
    ]
    evidence["checks"]["final_lambda_count"] = 0
    evidence["checks"]["final_lambdas"] = []
    for name in final_lambdas:
        try:
            cfg = lam.get_function_configuration(FunctionName=name)
            env = cfg.get("Environment", {}).get("Variables", {})
            evidence["checks"]["final_lambdas"].append(
                {
                    "name": name,
                    "state": cfg.get("State"),
                    "sns_configured": bool(env.get("SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN")),
                }
            )
            evidence["checks"]["final_lambda_count"] += 1
        except Exception as exc:
            evidence["checks"].setdefault("lambda_errors", []).append(f"{name}:{type(exc).__name__}")

    table_name = "ScoutMatchFootballOperationsAvidan"
    try:
        desc = ddb.describe_table(TableName=table_name)["Table"]
        evidence["checks"]["dynamodb_table_status"] = desc.get("TableStatus")
        evidence["checks"]["dynamodb_item_count"] = desc.get("ItemCount")
    except Exception as exc:
        evidence["checks"]["dynamodb_error"] = type(exc).__name__

    evidence["checks"]["sns_topic_suffix"] = "ScoutMatchManagementNotificationsAvidan"
    evidence["checks"]["sns_topic_verified"] = "MANUAL_REQUIRED"
    evidence["manual_validation_required"] = [
        "AWS Console screenshots for presentation slides (see SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md)",
        "Browser demo screenshots after live rehearsal",
    ]
    evidence["optional_future_extensions"] = [
        "SNS management notification (non-blocking; not required for course submission)",
    ]

    out_path = OUT / "scoutmatch_sanitized_aws_evidence.json"
    out_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    print(f"evidence_file={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
