#!/usr/bin/env python3
"""Live validation against the public EC2 Recruitment Advisor alias."""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
LEGACY_TOOLS = {"CalculateBudgetImpact", "EvaluateRightBackFit", "EvaluateBelowStrikerFit", "EvaluateForwardFit"}


def _load_alias_ids() -> tuple[str, str]:
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
        raise SystemExit("Missing agent or alias id")
    return agent_id, alias_id


def _agent_text(client, agent_id: str, alias_id: str, session_id: str, text: str) -> tuple[str, list[str]]:
    resp = client.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=text,
        enableTrace=True,
    )
    parts: list[str] = []
    tools: list[str] = []
    for event in resp.get("completion", []):
        if "chunk" in event and "bytes" in event["chunk"]:
            parts.append(event["chunk"]["bytes"].decode("utf-8", errors="replace"))
        trace = event.get("trace", {}).get("trace", {}).get("orchestrationTrace", {})
        inv = trace.get("invocationInput", {}).get("actionGroupInvocationInput", {})
        fn = inv.get("function") or inv.get("actionGroupName")
        if fn and fn not in tools:
            tools.append(str(fn))
    return "".join(parts), tools


def _selection_deny_event() -> dict:
    return {
        "function": "SubmitPlayerSelectionToManagement",
        "actionGroup": "ScoutMatchSelectionAgAvidan",
        "parameters": [
            {"name": "candidate_name", "value": "Ron Ben Ari"},
            {"name": "target_role", "value": "right-back"},
            {"name": "salary_eur", "value": "43000"},
        ],
        "confirmationState": "DENY",
    }


def _selection_confirm_event(*, candidate: str = "Tal Cohen", salary: int = 38000) -> dict:
    return {
        "function": "SubmitPlayerSelectionToManagement",
        "actionGroup": "ScoutMatchSelectionAgAvidan",
        "parameters": [
            {"name": "candidate_name", "value": candidate},
            {"name": "target_role", "value": "right-back"},
            {"name": "salary_eur", "value": str(salary)},
        ],
        "confirmationState": "CONFIRM",
    }


def _lambda_body(client, name: str, event: dict) -> dict:
    payload = json.loads(
        client.invoke(
            FunctionName=name,
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode("utf-8"),
        )["Payload"].read()
    )
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


def main() -> int:
    agent_id, alias_id = _load_alias_ids()
    cfg = Config(read_timeout=300, connect_timeout=60, retries={"max_attempts": 2})
    rt = boto3.client("bedrock-agent-runtime", region_name=REGION, config=cfg)
    lam = boto3.client("lambda", region_name=REGION, config=cfg)
    session = f"public-alias-{uuid.uuid4().hex[:12]}"
    results: dict[str, str] = {}
    blockers: list[str] = []

    tactical, tools_a = _agent_text(
        rt,
        agent_id,
        alias_id,
        session,
        "Our next match is against Barcelona. Our left-back is unavailable. "
        "We do not currently have a strong right-back within the budget. "
        "Our striker is aggressive and can play alone. "
        "Which formation and playing style do you recommend?",
    )
    legacy_hit = [t for t in tools_a if t in LEGACY_TOOLS]
    results["A_tactical"] = "PASS" if tactical.strip() and not legacy_hit else "FAIL"
    if legacy_hit:
        blockers.append(f"legacy_tools_in_tactical={legacy_hit}")

    select_text, tools_b = _agent_text(
        rt,
        agent_id,
        alias_id,
        session,
        "I choose Ron Ben Ari because he is the more aggressive option for this match. "
        "Submit the player selection to management.",
    )
    pre_submit_ok = (
        "PENDING_CONFIRMATION" in select_text.upper()
        or "confirm" in select_text.lower()
        or "confirmation" in select_text.lower()
    ) and "Player Selection Submitted" not in select_text
    results["B_selection_preconfirm"] = "PASS" if pre_submit_ok else "FAIL"
    if "CalculateBudgetImpact" in tools_b or "EvaluateRightBackFit" in tools_b:
        blockers.append(f"legacy_tools_on_selection={tools_b}")
        results["B_selection_preconfirm"] = "FAIL"

    deny_body = _lambda_body(lam, "ScoutMatchSubmitPlayerSelectionAvidan", _selection_deny_event())
    results["C_deny"] = "PASS" if deny_body.get("status") == "PENDING_CONFIRMATION" else "FAIL"

    fresh_session = f"public-alias-confirm-{uuid.uuid4().hex[:10]}"
    _agent_text(
        rt,
        agent_id,
        alias_id,
        fresh_session,
        "Our next match is against Barcelona. Our left-back is unavailable. "
        "We do not currently have a strong right-back within the budget. "
        "Our striker is aggressive and can play alone. Which formation do you recommend?",
    )
    pre, _ = _agent_text(
        rt,
        agent_id,
        alias_id,
        fresh_session,
        "I choose Ron Ben Ari because he is the more aggressive option. Submit to management.",
    )
    confirm_body = _lambda_body(lam, "ScoutMatchSubmitPlayerSelectionAvidan", _selection_confirm_event())
    repeat_body = _lambda_body(lam, "ScoutMatchSubmitPlayerSelectionAvidan", _selection_confirm_event())
    ok_confirm = confirm_body.get("status") == "PENDING_MANAGEMENT_APPROVAL" or confirm_body.get("idempotent")
    ok_idempotent = repeat_body.get("idempotent") is True or repeat_body.get("status") == confirm_body.get("status")
    results["D_confirm"] = "PASS" if ok_confirm else f"FAIL:{confirm_body.get('status')}"
    results["E_idempotent"] = "PASS" if ok_idempotent else "FAIL"

    lineup_pre, tools_line = _agent_text(
        rt,
        agent_id,
        alias_id,
        fresh_session,
        "Finalize the current demo 4-3-3 lineup with Ron Ben Ari at right-back.",
    )
    _lambda_body(
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
    lineup_confirm = _lambda_body(
        lam,
        "ScoutMatchFinalizeCurrentLineupAvidan",
        {
            "function": "FinalizeCurrentLineup",
            "actionGroup": "ScoutMatchLineupActionsAvidan",
            "parameters": [
                {"name": "formation", "value": "4-3-3"},
                {"name": "demo_lineup", "value": "true"},
                {"name": "opponent", "value": "Barcelona"},
            ],
            "confirmationState": "CONFIRM",
        },
    )
    results["F_lineup_preconfirm"] = (
        "PASS" if "confirm" in lineup_pre.lower() or "PENDING_CONFIRMATION" in lineup_pre.upper() else "FAIL"
    )
    results["F_lineup_confirm"] = (
        "PASS" if lineup_confirm.get("status") == "LINEUP_FINALIZED" else f"FAIL:{lineup_confirm.get('status')}"
    )

    board_text, tools_board = _agent_text(
        rt, agent_id, alias_id, fresh_session, "What is the current lineup now?"
    )
    board_body = _lambda_body(
        lam,
        "ScoutMatchGenerateLineupBoardAvidan",
        {
            "function": "GenerateCurrentLineupBoard",
            "actionGroup": "ScoutMatchLineupBoardActionsAvidan",
            "parameters": [],
        },
    )
    route_ok = "/api/recruitment-advisor/lineups/" in (board_text + json.dumps(board_body))
    results["G_lineup_board"] = "PASS" if board_body.get("status") == "LINEUP_BOARD_GENERATED" or route_ok else "FAIL"

    for key, value in results.items():
        if value != "PASS":
            blockers.append(f"{key}={value}")

    out = {"session": session, "results": results, "blockers": blockers, "blocker_count": len(blockers)}
    print(json.dumps(out, indent=2))
    print(f"BLOCKERS={len(blockers)}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    sys.exit(main())
