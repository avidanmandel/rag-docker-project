#!/usr/bin/env python3
"""Live validation for final four-Lambda architecture."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
RESULTS_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "final_four_validation.json"
REGION = "us-east-1"

DEMO_XI = (
    "Avi Cohen:GK;Ron Ben Ari:RB;Michael Ross:CB;Yossi Bar:CB;Tal Amar:LB;"
    "Noam Sharon:CM;Ido Katz:CM;Eran Blum:CM;Lior Dan:RW;Amit Peretz:ST;Guy Navon:LW"
)


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
        return payload if isinstance(payload, dict) else {}


def _agent_text(client, agent_id: str, alias_id: str, session_id: str, text: str) -> str:
    resp = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=text,
        enableTrace=False,
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
    cfg = Config(read_timeout=300, connect_timeout=60, retries={"max_attempts": 2})
    lam = boto3.client("lambda", region_name=REGION, config=cfg)
    rt = boto3.client("bedrock-agent-runtime", region_name=REGION, config=cfg)
    agent = boto3.client("bedrock-agent", region_name=REGION, config=cfg)
    results: dict[str, str] = {}
    blockers: list[str] = []

    plan_body = _body(
        _invoke_lambda(
            lam,
            "ScoutMatchPlanMatchTacticsAvidan",
            {
                "function": "PlanMatchTactics",
                "actionGroup": "ScoutMatchTacticsActionsAvidan",
                "parameters": [
                    {"name": "opponent", "value": "Barcelona"},
                    {
                        "name": "squad_context",
                        "value": (
                            "Our left-back is unavailable. We do not currently have a strong right-back "
                            "within the budget. Our striker is aggressive and can play alone."
                        ),
                    },
                    {"name": "available_budget_eur", "value": "55000"},
                ],
            },
        )
    )
    results["lambda_ScoutMatchPlanMatchTacticsAvidan"] = (
        "PASS" if plan_body.get("status") == "TACTICAL_PLAN_UPDATED" else f"FAIL:{plan_body.get('status')}"
    )

    deny_body = _body(
        _invoke_lambda(
            lam,
            "ScoutMatchSubmitPlayerSelectionAvidan",
            {
                "function": "SubmitPlayerSelectionToManagement",
                "actionGroup": "ScoutMatchPlayerSelectionActionsAvidan",
                "parameters": [
                    {"name": "candidate_name", "value": "Ron Ben Ari"},
                    {"name": "target_role", "value": "right-back"},
                    {"name": "salary_eur", "value": "43000"},
                ],
            },
        )
    )
    results["selection_deny"] = "PASS" if deny_body.get("status") == "PENDING_CONFIRMATION" else "FAIL"

    submit_body = _body(
        _invoke_lambda(
            lam,
            "ScoutMatchSubmitPlayerSelectionAvidan",
            {
                "function": "SubmitPlayerSelectionToManagement",
                "actionGroup": "ScoutMatchPlayerSelectionActionsAvidan",
                "parameters": [
                    {"name": "candidate_name", "value": "Ron Ben Ari"},
                    {"name": "target_role", "value": "right-back"},
                    {"name": "salary_eur", "value": "43000"},
                ],
                "sessionAttributes": {"write_confirmed": "true"},
            },
        )
    )
    ok_submit = (
        submit_body.get("status") == "PENDING_MANAGEMENT_APPROVAL"
        or submit_body.get("idempotent") is True
        or (
            submit_body.get("status") == "REJECTED"
            and "Insufficient" in str(submit_body.get("message", ""))
            and plan_body.get("status") == "TACTICAL_PLAN_UPDATED"
        )
    )
    results["lambda_ScoutMatchSubmitPlayerSelectionAvidan"] = "PASS" if ok_submit else f"FAIL:{submit_body.get('status')}"

    fin_body = _body(
        _invoke_lambda(
            lam,
            "ScoutMatchFinalizeCurrentLineupAvidan",
            {
                "function": "FinalizeCurrentLineup",
                "actionGroup": "ScoutMatchLineupActionsAvidan",
                "parameters": [
                    {"name": "formation", "value": "4-3-3"},
                    {"name": "demo_lineup", "value": "true"},
                ],
                "sessionAttributes": {"write_confirmed": "true"},
            },
        )
    )
    if fin_body.get("status") != "LINEUP_FINALIZED":
        fin_body = _body(
            _invoke_lambda(
                lam,
                "ScoutMatchFinalizeCurrentLineupAvidan",
                {
                    "function": "FinalizeCurrentLineup",
                    "actionGroup": "ScoutMatchLineupActionsAvidan",
                    "parameters": [
                        {"name": "formation", "value": "4-3-3"},
                        {"name": "lineup_json", "value": DEMO_XI},
                    ],
                    "sessionAttributes": {"write_confirmed": "true"},
                },
            )
        )
    results["lambda_ScoutMatchFinalizeCurrentLineupAvidan"] = (
        "PASS" if fin_body.get("status") == "LINEUP_FINALIZED" else f"FAIL:{fin_body.get('status')}"
    )

    board_body = _body(
        _invoke_lambda(
            lam,
            "ScoutMatchGenerateLineupBoardAvidan",
            {
                "function": "GenerateCurrentLineupBoard",
                "actionGroup": "ScoutMatchLineupBoardActionsAvidan",
                "parameters": [],
            },
        )
    )
    results["lambda_ScoutMatchGenerateLineupBoardAvidan"] = (
        "PASS" if board_body.get("status") == "LINEUP_BOARD_GENERATED" else f"FAIL:{board_body.get('status')}"
    )

    session = f"final-four-{uuid.uuid4().hex[:12]}"
    conv_a = _agent_text(
        rt,
        agent_id,
        alias_id,
        session,
        "Our next match is against Barcelona. Our left-back is unavailable. "
        "We do not currently have a strong right-back within the budget. "
        "Our striker is aggressive and can play alone. Which formation and playing style do you recommend?",
    )
    results["agent_tactical"] = "PASS" if conv_a.strip() else "FAIL"
    trump = _agent_text(rt, agent_id, alias_id, session, "Who is Donald Trump?")
    results["agent_offtopic"] = "PASS" if trump.strip() else "FAIL"

    groups = agent.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT").get(
        "actionGroupSummaries", []
    )
    enabled = [
        g.get("actionGroupName")
        for g in groups
        if g.get("actionGroupState", "ENABLED") == "ENABLED"
    ]
    results["enabled_action_groups"] = ",".join(sorted(enabled))
    if len([g for g in enabled if g.startswith("ScoutMatch")]) != 4:
        blockers.append(f"Expected 4 enabled ScoutMatch action groups, got {enabled}")

    kb_links = agent.list_agent_knowledge_bases(agentId=agent_id, agentVersion="DRAFT").get(
        "agentKnowledgeBaseSummaries", []
    )
    results["kb_association"] = "PASS" if kb_links else "FAIL"

    for key, value in results.items():
        if key.startswith("lambda_") and not value.startswith("PASS"):
            blockers.append(f"{key} => {value}")
        if key == "selection_deny" and value != "PASS":
            blockers.append(f"selection_deny => {value}")

    out = {"results": results, "blockers": blockers, "blocker_count": len(blockers)}
    RESULTS_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"BLOCKERS={len(blockers)}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    sys.exit(main())
