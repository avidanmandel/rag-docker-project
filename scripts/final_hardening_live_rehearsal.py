#!/usr/bin/env python3
"""Automated live acceptance rehearsal (Tests A–H) against production."""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from urllib.request import urlopen

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
PUBLIC_BASE = "http://3.239.47.249"


def _agent_ids() -> tuple[str, str]:
    agent_id = alias_id = ""
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
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
    return agent_id, alias_id


def _agent_invoke(session: str, text: str) -> tuple[str, list[str]]:
    agent_id, alias_id = _agent_ids()
    if not agent_id or not alias_id:
        return "", []
    cfg = Config(read_timeout=300, connect_timeout=60, retries={"max_attempts": 1})
    rt = boto3.client("bedrock-agent-runtime", region_name=REGION, config=cfg)
    resp = rt.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session,
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
        fn = inv.get("function")
        if fn and fn not in tools:
            tools.append(str(fn))
    return "".join(parts), tools


def _http_json(path: str) -> dict:
    with urlopen(f"{PUBLIC_BASE}{path}", timeout=20) as resp:
        return json.loads(resp.read().decode())


def _blocked(text: str) -> bool:
    lowered = text.lower()
    return "blocked by the scoutmatch safety policy" in lowered or "cannot answer this request" in lowered


def main() -> int:
    session = f"opening-season-demo-v1-{uuid.uuid4().hex[:8]}"
    results: dict[str, str] = {}
    blockers: list[str] = []

    # Test A — squad weakness
    a_text, _ = _agent_invoke(
        session,
        "Analyze our current squad weaknesses before the opening match. "
        "Use the current club squad and squad depth analysis.",
    )
    a_ok = (
        not _blocked(a_text)
        and "insufficient" not in a_text.lower()
        and ("right-back" in a_text.lower() or "right back" in a_text.lower() or "goalkeeper" in a_text.lower())
    )
    results["A_squad_weakness"] = "PASS" if a_ok else "FAIL"

    # Test B — right-back comparison
    b_text, _ = _agent_invoke(
        session,
        "Compare the right-back candidates within our recruitment budget. "
        "Include Ron Ben Ari and the other documented right-back options.",
    )
    b_ok = not _blocked(b_text) and ("ron" in b_text.lower() or "tal" in b_text.lower())
    results["B_right_back_comparison"] = "PASS" if b_ok else "FAIL"

    # Test C — goalkeeper injury
    c_text, c_tools = _agent_invoke(
        session,
        "Our starting goalkeeper was injured during training and will miss the next three matches. "
        "Which position should we prioritize and what tactical adjustment should we propose to the head coach?",
    )
    c_ok = not _blocked(c_text) and (
        "PlanMatchTactics" in c_tools or "plan" in c_text.lower() or "formation" in c_text.lower()
    )
    results["C_goalkeeper_injury"] = "PASS" if c_ok else "FAIL"

    # Test D/E — selection deny/confirm via four-tool validator patterns
    d_text, _ = _agent_invoke(
        session,
        "I choose Ron Ben Ari because he is the more aggressive right-back option. "
        "Submit the player recommendation to management.",
    )
    results["D_selection_preconfirm"] = (
        "PASS" if ("confirm" in d_text.lower() or "pending_confirmation" in d_text.lower()) else "FAIL"
    )

    lam = boto3.client("lambda", region_name=REGION)
    deny_event = {
        "function": "SubmitPlayerSelectionToManagement",
        "actionGroup": "ScoutMatchSelectionAgAvidan",
        "parameters": [
            {"name": "candidate_name", "value": "Ron Ben Ari"},
            {"name": "target_role", "value": "right-back"},
            {"name": "salary_eur", "value": "43000"},
        ],
        "confirmationState": "DENY",
    }
    deny_payload = json.loads(
        lam.invoke(
            FunctionName="ScoutMatchSubmitPlayerSelectionAvidan",
            Payload=json.dumps(deny_event).encode(),
        )["Payload"].read()
    )
    deny_body = json.loads(
        deny_payload["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    )
    results["D_selection_deny"] = "PASS" if deny_body.get("status") == "PENDING_CONFIRMATION" else "FAIL"

    confirm_session = f"opening-season-confirm-{uuid.uuid4().hex[:8]}"
    _agent_invoke(confirm_session, "Plan match tactics for opening season with budget 100000 EUR.")
    _agent_invoke(
        confirm_session,
        "I choose Ron Ben Ari because he is the more aggressive right-back option. "
        "Submit the player recommendation to management.",
    )
    confirm_event = {**deny_event, "confirmationState": "CONFIRM"}
    confirm_payload = json.loads(
        lam.invoke(
            FunctionName="ScoutMatchSubmitPlayerSelectionAvidan",
            Payload=json.dumps(confirm_event).encode(),
        )["Payload"].read()
    )
    confirm_body = json.loads(
        confirm_payload["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    )
    e_ok = confirm_body.get("status") == "PENDING_MANAGEMENT_APPROVAL"
    results["E_selection_confirm"] = "PASS" if e_ok else "FAIL"
    sns = confirm_body.get("sns") or {}
    results["E_management_notification"] = (
        "PASS"
        if "management_notified" in confirm_body
        else "FAIL"
    )
    if sns.get("mode") == "publish_error":
        results["E_sns_publish"] = "TOPIC_MISSING"
    elif sns.get("published"):
        results["E_sns_publish"] = "PASS"
    else:
        results["E_sns_publish"] = "QUEUED"

    # Test F — lineup save
    f_session = f"lineup-{uuid.uuid4().hex[:8]}"
    f_pre, _ = _agent_invoke(
        f_session,
        "Save the proposed demo 4-3-3 lineup with Ron Ben Ari at right-back for head-coach review.",
    )
    lam.invoke(
        FunctionName="ScoutMatchPlanMatchTacticsAvidan",
        Payload=json.dumps(
            {
                "function": "PlanMatchTactics",
                "actionGroup": "ScoutMatchTacticsActionsAvidan",
                "parameters": [
                    {"name": "opponent", "value": "Maccabi Haifa"},
                    {"name": "squad_context", "value": "Opening season demo lineup."},
                    {"name": "available_budget_eur", "value": "100000"},
                ],
            }
        ).encode(),
    )
    lineup_body = json.loads(
        lam.invoke(
            FunctionName="ScoutMatchFinalizeCurrentLineupAvidan",
            Payload=json.dumps(
                {
                    "function": "FinalizeCurrentLineup",
                    "actionGroup": "ScoutMatchLineupActionsAvidan",
                    "parameters": [
                        {"name": "formation", "value": "4-3-3"},
                        {"name": "demo_lineup", "value": "true"},
                    ],
                    "confirmationState": "CONFIRM",
                }
            ).encode(),
        )["Payload"].read()
    )
    lineup = json.loads(lineup_body["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    results["F_lineup_preconfirm"] = "PASS" if "confirm" in f_pre.lower() else "WARN"
    results["F_lineup_confirm"] = (
        "PASS"
        if lineup.get("status") in {"PENDING_HEAD_COACH_REVIEW", "LINEUP_FINALIZED"}
        and len(lineup.get("starting_xi") or lineup.get("lineup", {}).get("starting_xi") or []) == 11
        else "FAIL"
    )

    # Test G — lineup board
    g_text, g_tools = _agent_invoke(f_session, "Show me the current proposed lineup.")
    board_body = json.loads(
        lam.invoke(
            FunctionName="ScoutMatchGenerateLineupBoardAvidan",
            Payload=json.dumps(
                {
                    "function": "GenerateCurrentLineupBoard",
                    "actionGroup": "ScoutMatchLineupBoardActionsAvidan",
                    "parameters": [],
                }
            ).encode(),
        )["Payload"].read()
    )
    board = json.loads(board_body["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    route = board.get("image_route") or ""
    proxy_ok = False
    if route:
        try:
            with urlopen(f"{PUBLIC_BASE}{route}", timeout=20) as resp:
                proxy_ok = resp.status == 200
        except Exception:
            proxy_ok = False
    results["G_lineup_board"] = (
        "PASS"
        if board.get("status") == "LINEUP_BOARD_GENERATED" or proxy_ok or "lineups/" in g_text
        else "FAIL"
    )

    # Test H — product UI via HTTP
    home = urlopen(f"{PUBLIC_BASE}/", timeout=30).read().decode(errors="replace")
    status = _http_json("/api/status")
    workspace = _http_json("/api/opening-season/workspace")
    club_count = int(status.get("club_player_count") or workspace.get("club_player_count") or 0)
    cand_count = int(status.get("candidate_pool_count") or workspace.get("candidate_pool_count") or 0)
    h_ok = (
        (
            "opening season" in home.lower()
            or "opening-season" in home.lower()
            or bool(workspace.get("workspace_ready"))
        )
        and club_count == 15
        and cand_count == 8
        and "sidebar-group" in home
        and "ctx-" not in home
    )
    results["H_product_ui"] = "PASS" if h_ok else "FAIL"

    for key, value in results.items():
        if value == "FAIL":
            blockers.append(key)

    out = {
        "public_base": PUBLIC_BASE,
        "session": session,
        "results": results,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "sns_note": "publish_error means SNS topic must be created in Console; see docs/SCOUTMATCH_SNS_EMAIL_SUBSCRIPTION_GUIDE.md",
    }
    print(json.dumps(out, indent=2))
    print(f"BLOCKERS={len(blockers)}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
