#!/usr/bin/env python3
"""Comprehensive stabilization probes for legacy $LATEST and v2-staging aliases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "stabilization_probe_report.json"
REGION = "us-east-1"
V2_ALIAS = "scoutmatch-v2-staging"


def _body(raw: dict) -> dict:
    try:
        text = (
            raw.get("response", {})
            .get("functionResponse", {})
            .get("responseBody", {})
            .get("TEXT", {})
            .get("body", "{}")
        )
        return json.loads(text) if isinstance(text, str) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def invoke(lam, target: str, event: dict) -> dict:
    resp = lam.invoke(
        FunctionName=target,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode("utf-8"),
    )
    raw = json.loads(resp["Payload"].read())
    if "FunctionError" in resp:
        return {"status": "FUNCTION_ERROR", "error": raw}
    return _body(raw)


def main() -> int:
    lam = boto3.client("lambda", region_name=REGION)
    report: dict = {"legacy_latest": {}, "v2_staging": {}}

    legacy_tactics = invoke(
        lam,
        "ScoutMatchPlanMatchTacticsAvidan",
        {
            "function": "PlanMatchTactics",
            "actionGroup": "ScoutMatchTacticsActionsAvidan",
            "parameters": [
                {"name": "squad_context", "value": "Need right-back cover"},
                {"name": "opponent", "value": "Barcelona"},
            ],
        },
    )
    report["legacy_latest"]["plan_match_tactics"] = legacy_tactics.get("status")

    legacy_selection_prep = invoke(
        lam,
        "ScoutMatchSubmitPlayerSelectionAvidan",
        {
            "function": "SubmitPlayerSelectionToManagement",
            "actionGroup": "ScoutMatchSelectionAgAvidan",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    report["legacy_latest"]["selection_pre_confirm"] = legacy_selection_prep.get("status")

    v2_target = f"ScoutMatchPlanMatchTacticsAvidan:{V2_ALIAS}"
    transfer_prep = invoke(
        lam,
        v2_target,
        {
            "function": "OpenTransferOutReviewCase",
            "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
        },
    )
    transfer_deny = invoke(
        lam,
        v2_target,
        {
            "function": "OpenTransferOutReviewCase",
            "confirmationState": "DENY",
            "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
        },
    )
    transfer_confirm = invoke(
        lam,
        v2_target,
        {
            "function": "OpenTransferOutReviewCase",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
        },
    )
    transfer_confirm2 = invoke(
        lam,
        v2_target,
        {
            "function": "OpenTransferOutReviewCase",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
        },
    )
    report["v2_staging"]["transfer_out"] = {
        "pre_confirm": transfer_prep.get("status"),
        "deny": transfer_deny.get("status"),
        "confirm": transfer_confirm.get("status"),
        "estimated_release": transfer_confirm.get("estimated_budget_release_eur"),
        "idempotent": transfer_confirm2.get("idempotent"),
    }

    mission_target = f"ScoutMatchFinalizeCurrentLineupAvidan:{V2_ALIAS}"
    mission_prep = invoke(
        lam,
        mission_target,
        {
            "function": "CreateAndReviewScoutingMission",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    mission_deny = invoke(
        lam,
        mission_target,
        {
            "function": "CreateAndReviewScoutingMission",
            "confirmationState": "DENY",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    mission_confirm = invoke(
        lam,
        mission_target,
        {
            "function": "CreateAndReviewScoutingMission",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    mission_confirm2 = invoke(
        lam,
        mission_target,
        {
            "function": "CreateAndReviewScoutingMission",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    review = invoke(
        lam,
        mission_target,
        {
            "function": "CreateAndReviewScoutingMission",
            "parameters": [
                {"name": "candidate_name", "value": "Ron Ben Ari"},
                {"name": "mission_mode", "value": "REVIEW_COMPLETED_MISSION"},
            ],
        },
    )
    report["v2_staging"]["scouting_mission"] = {
        "pre_confirm": mission_prep.get("status"),
        "deny": mission_deny.get("status"),
        "confirm_status": mission_confirm.get("status"),
        "calendar_label": bool(mission_confirm.get("calendar_label")),
        "invite_key": bool(mission_confirm.get("calendar_invite_key")),
        "idempotent": mission_confirm2.get("idempotent"),
        "review_status": review.get("status"),
        "review_label": review.get("report_label", ""),
        "report_type": review.get("report_type"),
    }

    critical_target = f"ScoutMatchSubmitPlayerSelectionAvidan:{V2_ALIAS}"
    critical_prep = invoke(
        lam,
        critical_target,
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    critical_deny = invoke(
        lam,
        critical_target,
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "confirmationState": "DENY",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    critical_confirm = invoke(
        lam,
        critical_target,
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "confirmationState": "CONFIRM",
            "parameters": [
                {"name": "candidate_name", "value": "Ron Ben Ari"},
                {"name": "salary_eur", "value": "43000"},
            ],
        },
    )
    critical_confirm2 = invoke(
        lam,
        critical_target,
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
    )
    report["v2_staging"]["critical_decision"] = {
        "pre_confirm": critical_prep.get("status"),
        "deny": critical_deny.get("status"),
        "confirm_status": critical_confirm.get("status"),
        "reserved": critical_confirm.get("reserved_amount_eur"),
        "remaining": critical_confirm.get("remaining_budget_eur"),
        "email_message": critical_confirm.get("email_status_message", ""),
        "idempotent": critical_confirm2.get("idempotent"),
    }

    board_target = f"ScoutMatchGenerateLineupBoardAvidan:{V2_ALIAS}"
    board_prep = invoke(
        lam,
        board_target,
        {
            "function": "GenerateVisualSquadAndLineupBoard",
            "parameters": [{"name": "board_mode", "value": "SAVE_AND_RENDER"}, {"name": "demo_lineup", "value": "true"}],
        },
    )
    board_deny = invoke(
        lam,
        board_target,
        {
            "function": "GenerateVisualSquadAndLineupBoard",
            "confirmationState": "DENY",
            "parameters": [{"name": "board_mode", "value": "SAVE_AND_RENDER"}, {"name": "demo_lineup", "value": "true"}],
        },
    )
    board_confirm = invoke(
        lam,
        board_target,
        {
            "function": "GenerateVisualSquadAndLineupBoard",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "board_mode", "value": "SAVE_AND_RENDER"}, {"name": "demo_lineup", "value": "true"}],
        },
    )
    board_render = invoke(
        lam,
        board_target,
        {
            "function": "GenerateVisualSquadAndLineupBoard",
            "parameters": [{"name": "board_mode", "value": "RENDER_CURRENT"}],
        },
    )
    board_none = invoke(
        lam,
        board_target,
        {
            "function": "GenerateVisualSquadAndLineupBoard",
            "parameters": [{"name": "board_mode", "value": "RENDER_CURRENT"}],
            "sessionAttributes": {"force_empty_scope": "true"},
        },
    )
    report["v2_staging"]["lineup_board"] = {
        "pre_confirm": board_prep.get("status"),
        "deny": board_deny.get("status"),
        "confirm_status": board_confirm.get("status"),
        "player_count": board_confirm.get("player_count"),
        "remaining_budget": board_render.get("remaining_confirmed_budget_eur"),
        "render_status": board_render.get("status"),
        "no_lineup_status": board_none.get("status"),
        "public_s3_url": board_confirm.get("public_url") or board_render.get("public_url"),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
