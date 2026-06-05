"""Course simplified design: exactly four user-facing Agent Tools."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ["SCOUTMATCH_WORKFLOW_INPROCESS"] = "true"

_ROOT = Path(__file__).resolve().parents[1] / "lambdas"
_NATIVE = _ROOT / "native_tools" / "lambda_function.py"
_OPS = _ROOT / "football_operations" / "lambda_function.py"
_COMMON = _ROOT / "common"
for p in (str(_COMMON), str(_ROOT / "native_tools"), str(_ROOT / "football_operations")):
    if p not in sys.path:
        sys.path.insert(0, p)

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from football_operations_apply import (  # noqa: E402
    INTERNAL_AGENT_HELPERS,
    NATIVE_AGENT_FUNCTIONS_SIMPLIFIED,
)

_spec_native = importlib.util.spec_from_file_location("native_tools", _NATIVE)
native = importlib.util.module_from_spec(_spec_native)
assert _spec_native.loader is not None
_spec_native.loader.exec_module(native)

_spec_ops = importlib.util.spec_from_file_location("football_ops", _OPS)
ops = importlib.util.module_from_spec(_spec_ops)
assert _spec_ops.loader is not None
_spec_ops.loader.exec_module(ops)


def test_exactly_four_user_facing_tools_defined():
    assert len(NATIVE_AGENT_FUNCTIONS_SIMPLIFIED) == 4
    assert set(NATIVE_AGENT_FUNCTIONS_SIMPLIFIED) == set(native._AGENT_FUNCTIONS.keys())


def test_internal_helpers_not_user_facing():
    for helper in (
        "CalculateBudgetImpact",
        "AddCandidateToShortlist",
        "StartCandidateReviewWorkflow",
    ):
        assert helper in INTERNAL_AGENT_HELPERS
        assert helper not in native._AGENT_FUNCTIONS


def test_removed_recruitment_tools_not_routed():
    event = {
        "function": "AddCandidateToShortlist",
        "actionGroup": "ScoutMatchNativeActionsAvidan",
        "parameters": [],
    }
    resp = native.lambda_handler(event, None)
    body = json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    assert body["status"] == "FAILURE"


def test_budget_helper_used_internally_on_confirm():
    from operations_store import clear_local_store

    clear_local_store()
    ops.lambda_handler(
        {
            "function": "UpdateSquadPlanningContext",
            "actionGroup": "ScoutMatchFootballOperationsActionsAvidan",
            "parameters": [
                {"name": "opponent", "value": "Barcelona"},
                {"name": "preferred_formation", "value": "4-3-3"},
                {"name": "available_budget_eur", "value": "55000"},
            ],
        },
        None,
    )
    resp = ops.lambda_handler(
        {
            "function": "SubmitPlayerSelectionToManagement",
            "actionGroup": "ScoutMatchFootballOperationsActionsAvidan",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
            "sessionAttributes": {"write_confirmed": "true"},
        },
        None,
    )
    body = json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    assert body["status"] in {"RESERVED", "ALREADY_RESERVED", "REJECTED"}
    assert (
        "budget_decision" in body
        or body["status"] in {"REJECTED", "ALREADY_RESERVED"}
    )
