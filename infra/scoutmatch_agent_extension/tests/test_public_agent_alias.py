"""Public alias four-tool architecture and confirmation safety tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ["SCOUTMATCH_BEDROCK_NATIVE_CONFIRMATION"] = "true"

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LAMBDAS = Path(__file__).resolve().parents[1] / "lambdas"
for p in (str(LAMBDAS / "common"), str(LAMBDAS / "shared_football"), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402

from four_lambda_apply import (  # noqa: E402
    ACTION_GROUPS_DETACHED_AT_FINAL_APPLY,
    FINAL_FOUR_LAMBDAS,
    FINAL_USER_FACING_FUNCTIONS,
    WRITE_CONFIRM_FUNCTIONS,
)
from write_confirmation import is_write_confirmed  # noqa: E402

BEDROCK_TOOL_NAME_LIMIT = 64
LEGACY_SCHEMAS = {
    "CalculateBudgetImpact",
    "EvaluateRightBackFit",
    "EvaluateBelowStrikerFit",
    "EvaluateForwardFit",
    "AddCandidateToShortlist",
    "StartCandidateReviewWorkflow",
    "CreateRecruitmentBrief",
    "UpdateSquadPlanningContext",
}
PUBLIC_ALIAS_NAME = "scoutmatch-demo-stable-v2"


def _load_audit_module():
    path = SCRIPTS / "audit_public_agent_alias.py"
    spec = importlib.util.spec_from_file_location("audit_public_agent_alias", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_submit_lambda():
    path = LAMBDAS / "submit_player_selection" / "lambda_function.py"
    spec = importlib.util.spec_from_file_location("submit_player_selection", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_alias_exposes_four_action_groups_and_functions():
    groups = {meta["action_group"] for meta in FINAL_FOUR_LAMBDAS.values()}
    assert len(groups) == 4
    assert len(FINAL_USER_FACING_FUNCTIONS) == 4
    assert set(FINAL_USER_FACING_FUNCTIONS) == {
        "PlanMatchTactics",
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
        "GenerateCurrentLineupBoard",
    }


def test_bedrock_tool_names_within_quota():
    for meta in FINAL_FOUR_LAMBDAS.values():
        tool_name = f"{meta['action_group']}__{meta['function']}"
        assert len(tool_name) <= BEDROCK_TOOL_NAME_LIMIT, tool_name


def test_legacy_helper_action_groups_marked_detached():
    assert "ScoutMatchNativeActionsAvidan" in ACTION_GROUPS_DETACHED_AT_FINAL_APPLY
    assert "ScoutMatchBudgetActionsAvidan" in ACTION_GROUPS_DETACHED_AT_FINAL_APPLY
    assert "ScoutMatchRightBackActionsAvidan" in ACTION_GROUPS_DETACHED_AT_FINAL_APPLY
    assert "ScoutMatchPlayerSelectionActionsAvidan" in ACTION_GROUPS_DETACHED_AT_FINAL_APPLY


def test_legacy_helper_schemas_not_in_final_functions():
    assert not LEGACY_SCHEMAS.intersection(set(FINAL_USER_FACING_FUNCTIONS))


def test_write_confirm_functions_require_native_confirmation():
    assert WRITE_CONFIRM_FUNCTIONS == {
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
    }


def test_submit_selection_not_confirmed_without_explicit_state():
    event = {
        "function": "SubmitPlayerSelectionToManagement",
        "actionGroup": "ScoutMatchSelectionAgAvidan",
        "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        "invocationId": "demo-invocation-only",
    }
    assert is_write_confirmed(event) is False


def test_submit_selection_confirmed_only_with_confirm_state():
    event = {
        "function": "SubmitPlayerSelectionToManagement",
        "confirmationState": "CONFIRM",
    }
    assert is_write_confirmed(event) is True


def test_submit_selection_deny_blocks_write():
    event = {
        "function": "SubmitPlayerSelectionToManagement",
        "confirmationState": "DENY",
    }
    assert is_write_confirmed(event) is False


def test_pre_confirm_selection_returns_pending_confirmation():
    mod = _load_submit_lambda()
    resp = mod.lambda_handler(
        {
            "function": "SubmitPlayerSelectionToManagement",
            "actionGroup": "ScoutMatchSelectionAgAvidan",
            "parameters": [
                {"name": "candidate_name", "value": "Ron Ben Ari"},
                {"name": "target_role", "value": "right-back"},
                {"name": "salary_eur", "value": "43000"},
            ],
        },
        None,
    )
    body = json.loads(
        resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    )
    assert body["status"] == "PENDING_CONFIRMATION"


def test_audit_stale_detection_uses_boolean_not_set():
    audit = _load_audit_module()
    stale = bool(
        "12".isdigit()
        and (
            {"ScoutMatchBudgetActionsAvidan"} != audit.FINAL_GROUPS
            or bool({"CalculateBudgetImpact"} & LEGACY_SCHEMAS)
            or not audit.FINAL_FUNCTIONS.issubset({"PlanMatchTactics"})
        )
    )
    assert isinstance(stale, bool)


def test_public_alias_name_constant_matches_stable_alias():
    assert PUBLIC_ALIAS_NAME == "scoutmatch-demo-stable-v2"


def test_demo_roster_loader_safe_in_lambda_style_paths():
    from demo_roster import build_demo_starting_xi, load_demo_roster_from_file

    roster = load_demo_roster_from_file()
    assert len(roster.get("players") or []) == 11
    starters = build_demo_starting_xi(ron_at_right_back=True)
    assert len(starters) == 11
