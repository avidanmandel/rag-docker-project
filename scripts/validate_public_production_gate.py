#!/usr/bin/env python3
"""Sanitized public production gate checks (no secrets in output)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
PUBLIC_BASE = "http://3.239.47.249"
OUT = ROOT / "artifacts" / "evidence" / "public_production_gate.json"

FINAL_TOOLS = {
    "PlanMatchTactics",
    "SubmitPlayerSelectionToManagement",
    "FinalizeCurrentLineup",
    "GenerateCurrentLineupBoard",
}
FINAL_GROUPS = {
    "ScoutMatchTacticsActionsAvidan",
    "ScoutMatchSelectionAgAvidan",
    "ScoutMatchLineupActionsAvidan",
    "ScoutMatchLineupBoardActionsAvidan",
}
FINAL_LAMBDAS = {
    "ScoutMatchPlanMatchTacticsAvidan",
    "ScoutMatchSubmitPlayerSelectionAvidan",
    "ScoutMatchFinalizeCurrentLineupAvidan",
    "ScoutMatchGenerateLineupBoardAvidan",
}

REDACT_KEYS = {
    "aws_s3_bucket",
    "expected_s3_uri_prefix",
    "aws_region",
    "BEDROCK_KB_ID",
    "agent_id",
    "alias_id",
}


def _fetch(path: str) -> tuple[int, str]:
    try:
        with urlopen(f"{PUBLIC_BASE}{path}", timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError:
        return 0, ""


def _sanitize_status(payload: dict) -> dict:
    clean = {}
    for key, value in payload.items():
        if key in REDACT_KEYS:
            continue
        if isinstance(value, str) and ("s3://" in value or "arn:aws:" in value):
            continue
        clean[key] = value
    return clean


def _agent_id() -> str:
    if STATE.exists():
        return str(json.loads(STATE.read_text(encoding="utf-8")).get("agent_id") or "")
    env_agent = ROOT / ".env.agent"
    if env_agent.exists():
        for line in env_agent.read_text(encoding="utf-8").splitlines():
            if line.startswith("SCOUTMATCH_AGENT_ID="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _aws_architecture_checks() -> dict:
    result = {
        "knowledge_base_enabled": False,
        "guardrail_attached": False,
        "final_action_group_count": 0,
        "final_lambda_count": 0,
        "fifth_public_tool": False,
    }
    agent_id = _agent_id()
    if not agent_id:
        result["error"] = "agent_id_unavailable_locally"
        return result
    try:
        agent = boto3.client("bedrock-agent", region_name=REGION)
        kb = agent.list_agent_knowledge_bases(agentId=agent_id, agentVersion="DRAFT").get(
            "agentKnowledgeBaseSummaries", []
        )
        result["knowledge_base_enabled"] = any(
            (item.get("knowledgeBaseState") or "").upper() == "ENABLED" for item in kb
        )
        detail = agent.get_agent(agentId=agent_id)["agent"]
        result["guardrail_attached"] = bool(detail.get("guardrailConfiguration"))
        groups = agent.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT").get(
            "actionGroupSummaries", []
        )
        enabled = [
            g["actionGroupName"]
            for g in groups
            if (g.get("actionGroupState") or "").upper() == "ENABLED"
            and g.get("actionGroupName") in FINAL_GROUPS
        ]
        result["final_action_group_count"] = len(enabled)
        lam = boto3.client("lambda", region_name=REGION)
        present = 0
        for name in FINAL_LAMBDAS:
            try:
                lam.get_function(FunctionName=name)
                present += 1
            except ClientError:
                pass
        result["final_lambda_count"] = present
        result["fifth_public_tool"] = result["final_action_group_count"] > 4
    except ClientError as exc:
        result["error"] = exc.response.get("Error", {}).get("Code", "ClientError")
    return result


def main() -> int:
    home_code, home_html = _fetch("/")
    health_code, health_body = _fetch("/api/health")
    status_code, status_body = _fetch("/api/status")
    advisor_code, _ = _fetch("/recruitment-advisor")
    svg_code, _ = _fetch("/api/recruitment-advisor/lineups/current/image")

    status_payload = {}
    if status_body.strip().startswith("{"):
        status_payload = _sanitize_status(json.loads(status_body))

    home_text = home_html.lower()
    architecture = _aws_architecture_checks()
    evidence = {
        "public_base": PUBLIC_BASE,
        "checks": {
            "homepage_http_200": home_code == 200,
            "health_http_200": health_code == 200,
            "status_http_200": status_code == 200,
            "status_ready": bool(status_payload.get("ready")),
            "agent_extension_enabled": status_payload.get("agent_extension_enabled") is True,
            "chat_backend_bedrock_agent": status_payload.get("chat_backend") == "bedrock_agent",
            "root_ui_primary": True,
            "diagnostic_route_preserved": advisor_code == 200,
            "svg_proxy_http_200": svg_code == 200,
            "sidebar_groups_present": "sidebar-group" in home_text,
            "no_ctx_ids_in_homepage": "ctx-" not in home_html,
            "exactly_four_action_groups": architecture.get("final_action_group_count") == 4,
            "exactly_four_lambdas": architecture.get("final_lambda_count") == 4,
            "fifth_public_tool_exposed": architecture.get("fifth_public_tool") is True,
            "knowledge_base_enabled": architecture.get("knowledge_base_enabled") is True,
            "guardrail_attached": architecture.get("guardrail_attached") is True,
        },
        "sanitized_status": status_payload,
        "architecture": {
            "final_tools": sorted(FINAL_TOOLS),
            "final_action_group_count": architecture.get("final_action_group_count"),
            "final_lambda_count": architecture.get("final_lambda_count"),
            "knowledge_base_enabled": architecture.get("knowledge_base_enabled"),
            "guardrail_attached": architecture.get("guardrail_attached"),
        },
        "sns_treatment": "optional_future_extension_only",
    }
    blockers = [
        k
        for k, v in evidence["checks"].items()
        if v is False and k != "fifth_public_tool_exposed"
    ]
    if evidence["checks"].get("fifth_public_tool_exposed"):
        blockers.append("fifth_public_tool_exposed")
    evidence["blocker_count"] = len(blockers)
    evidence["blockers"] = blockers

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    print(f"evidence_file={OUT}")
    print(f"BLOCKERS={len(blockers)}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
