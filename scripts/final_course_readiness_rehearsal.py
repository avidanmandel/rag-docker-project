#!/usr/bin/env python3
"""Final course readiness live rehearsal (Flows A–G). SNS is not validated."""

from __future__ import annotations

import json
import subprocess
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


def _blocked(text: str) -> bool:
    lowered = text.lower()
    return "blocked by the scoutmatch safety policy" in lowered or "cannot answer this request" in lowered


def _selection_event(*, state: str, candidate: str = "Ron Ben Ari", salary: int = 43000) -> dict:
    return {
        "function": "SubmitPlayerSelectionToManagement",
        "actionGroup": "ScoutMatchSelectionAgAvidan",
        "parameters": [
            {"name": "candidate_name", "value": candidate},
            {"name": "target_role", "value": "right-back"},
            {"name": "salary_eur", "value": str(salary)},
        ],
        "confirmationState": state,
    }


def _invoke_selection(event: dict) -> dict:
    lam = boto3.client("lambda", region_name=REGION)
    payload = json.loads(
        lam.invoke(
            FunctionName="ScoutMatchSubmitPlayerSelectionAvidan",
            Payload=json.dumps(event).encode(),
        )["Payload"].read()
    )
    return json.loads(payload["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def _flow_g_unit_pass() -> bool:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_opening_season_stabilization.py::test_lineup_scoped_to_active_demo_season_only",
            "-q",
            "--tb=no",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    results: dict[str, str] = {}
    blockers: list[str] = []

    # Flow A
    session_a = f"course-a-{uuid.uuid4().hex[:8]}"
    a_text, _ = _agent_invoke(
        session_a,
        "Analyze our current squad weaknesses before the opening match. "
        "Use the current club squad and squad depth analysis.",
    )
    a_ok = (
        not _blocked(a_text)
        and "insufficient" not in a_text.lower()
        and ("right-back" in a_text.lower() or "right back" in a_text.lower() or "goalkeeper" in a_text.lower())
    )
    results["A_squad_weakness"] = "PASS" if a_ok else "FAIL"

    # Flow B
    session_b = f"course-b-{uuid.uuid4().hex[:8]}"
    b_text, _ = _agent_invoke(
        session_b,
        "Compare the right-back candidates within our recruitment budget. "
        "Include Ron Ben Ari and Tal Cohen.",
    )
    b_ok = not _blocked(b_text) and "ron" in b_text.lower() and "tal" in b_text.lower()
    results["B_right_back_comparison"] = "PASS" if b_ok else "FAIL"

    # Flow C
    session_c = f"course-c-{uuid.uuid4().hex[:8]}"
    c_text, c_tools = _agent_invoke(
        session_c,
        "Our starting goalkeeper was injured during training and will miss the next three matches. "
        "Which position should we prioritize and what tactical adjustment should we propose to the head coach?",
    )
    c_ok = not _blocked(c_text) and (
        "PlanMatchTactics" in c_tools or "goalkeeper" in c_text.lower() or "formation" in c_text.lower()
    )
    results["C_goalkeeper_injury"] = "PASS" if c_ok else "FAIL"

    # Flow D pre-confirm
    session_d = f"course-d-{uuid.uuid4().hex[:8]}"
    d_pre, _ = _agent_invoke(
        session_d,
        "I choose Ron Ben Ari because he is the more aggressive right-back option. "
        "Submit the player recommendation to management.",
    )
    results["D_preconfirm"] = "PASS" if "confirm" in d_pre.lower() else "FAIL"

    # Flow D Deny (fresh Lambda path)
    deny_body = _invoke_selection(_selection_event(state="DENY"))
    results["D_deny"] = "PASS" if deny_body.get("status") == "PENDING_CONFIRMATION" else "FAIL"

    # Flow D Confirm (fresh candidate to avoid idempotent path)
    _agent_invoke(session_d, "Plan match tactics for opening season with budget 100000 EUR.")
    confirm_body = _invoke_selection(_selection_event(state="CONFIRM", candidate="Tal Cohen", salary=38000))
    e_ok = confirm_body.get("status") == "PENDING_MANAGEMENT_APPROVAL"
    results["D_confirm"] = "PASS" if e_ok else "FAIL"
    results["D_budget_reserved"] = (
        "PASS"
        if confirm_body.get("reserved_amount_eur") == 38000
        and confirm_body.get("remaining_budget_eur") is not None
        else "FAIL"
    )

    # Flow D idempotency
    repeat_body = _invoke_selection(_selection_event(state="CONFIRM", candidate="Tal Cohen", salary=38000))
    results["D_idempotent"] = (
        "PASS"
        if repeat_body.get("idempotent") and repeat_body.get("status") == "PENDING_MANAGEMENT_APPROVAL"
        else "FAIL"
    )

    # Flow E lineup save
    session_e = f"course-e-{uuid.uuid4().hex[:8]}"
    e_pre, _ = _agent_invoke(
        session_e,
        "Save the proposed demo 4-3-3 lineup with Ron Ben Ari at right-back for head-coach review.",
    )
    lam = boto3.client("lambda", region_name=REGION)
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
    lineup_payload = json.loads(
        lam.invoke(
            FunctionName="ScoutMatchFinalizeCurrentLineupAvidan",
            Payload=json.dumps(
                {
                    "function": "FinalizeCurrentLineup",
                    "actionGroup": "ScoutMatchLineupActionsAvidan",
                    "parameters": [{"name": "formation", "value": "4-3-3"}, {"name": "demo_lineup", "value": "true"}],
                    "confirmationState": "CONFIRM",
                }
            ).encode(),
        )["Payload"].read()
    )
    lineup = json.loads(lineup_payload["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    xi = lineup.get("starting_xi") or lineup.get("lineup", {}).get("starting_xi") or []
    results["E_lineup_preconfirm"] = "PASS" if "confirm" in e_pre.lower() else "WARN"
    results["E_lineup_confirm"] = (
        "PASS"
        if lineup.get("status") in {"PENDING_HEAD_COACH_REVIEW", "LINEUP_FINALIZED"}
        and len(xi) == 11
        else "FAIL"
    )

    # Flow F lineup board
    board_payload = json.loads(
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
    board = json.loads(board_payload["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    route = board.get("image_route") or ""
    proxy_ok = False
    if route:
        try:
            with urlopen(f"{PUBLIC_BASE}{route}", timeout=20) as resp:
                proxy_ok = resp.status == 200
        except Exception:
            proxy_ok = False
    results["F_lineup_board"] = (
        "PASS"
        if board.get("status") == "LINEUP_BOARD_GENERATED"
        and (board.get("player_count") == 11 or len(board.get("starting_xi") or []) == 11 or proxy_ok)
        else "FAIL"
    )
    results["F_svg_proxy"] = "PASS" if proxy_ok else "FAIL"
    results["F_no_public_s3"] = "PASS" if route.startswith("/api/") and "s3.amazonaws.com" not in route else "FAIL"

    # Flow G clean no-lineup (unit-isolated scope; shared demo may already have lineup)
    results["G_clean_no_lineup"] = "PASS" if _flow_g_unit_pass() else "FAIL"

    for key, value in results.items():
        if value == "FAIL":
            blockers.append(key)

    out = {
        "public_base": PUBLIC_BASE,
        "results": results,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "sns_note": "SNS frozen as optional; not validated in this rehearsal",
    }
    print(json.dumps(out, indent=2))
    print(f"BLOCKERS={len(blockers)}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
