"""Final four-Lambda architecture local tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ.pop("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", None)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LAMBDAS = Path(__file__).resolve().parents[1] / "lambdas"
for p in (str(LAMBDAS / "common"), str(LAMBDAS / "shared_football"), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402

_SHARED_OPS = LAMBDAS / "shared_football" / "operations_store.py"
_SHARED_STORE = None
_SHARED_MODULES = (
    "budget_ledger",
    "tactical_planner",
    "player_selection",
)


def _shared_operations_store():
    global _SHARED_STORE
    if _SHARED_STORE is None:
        spec = importlib.util.spec_from_file_location("operations_store", _SHARED_OPS)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _SHARED_STORE = module
    return _SHARED_STORE


def _evict_shared_modules() -> None:
    for name in _SHARED_MODULES:
        sys.modules.pop(name, None)


def _reload_shared_modules() -> None:
    for name in _SHARED_MODULES:
        path = LAMBDAS / "shared_football" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        sys.modules[name] = module


@pytest.fixture(autouse=True)
def _legacy_four_lambda_env():
    os.environ.pop("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", None)
    import importlib

    import four_lambda_apply

    importlib.reload(four_lambda_apply)
    yield


@pytest.fixture(autouse=True)
def _isolated_shared_store():
    previous = sys.modules.get("operations_store")
    store = _shared_operations_store()
    sys.modules["operations_store"] = store
    _evict_shared_modules()
    _reload_shared_modules()
    store.clear_local_store()
    yield
    store.clear_local_store()
    _evict_shared_modules()
    if previous is not None:
        sys.modules["operations_store"] = previous
    else:
        sys.modules.pop("operations_store", None)

from four_lambda_apply import FINAL_FOUR_LAMBDAS, FINAL_USER_FACING_FUNCTIONS  # noqa: E402


def _load_lambda(folder: str):
    path = LAMBDAS / folder / "lambda_function.py"
    spec = importlib.util.spec_from_file_location(folder, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def test_four_lambdas_four_action_groups_one_function_each():
    assert len(FINAL_FOUR_LAMBDAS) == 4
    groups = {m["action_group"] for m in FINAL_FOUR_LAMBDAS.values()}
    assert len(groups) == 4
    assert set(FINAL_USER_FACING_FUNCTIONS) == {
        "PlanMatchTactics",
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
        "GenerateCurrentLineupBoard",
    }


def test_plan_match_tactics_recommends_541():
    mod = _load_lambda("plan_match_tactics")
    resp = mod.lambda_handler(
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
        None,
    )
    body = _body(resp)
    assert body["status"] == "TACTICAL_PLAN_UPDATED"
    assert body["recommended_formation"] == "5-4-1"


def test_submit_selection_uses_shared_budget_module():
    from player_selection import submit_selection
    from tactical_planner import plan_match_tactics

    plan_match_tactics(
        opponent="Barcelona",
        squad_context="weak right-back within budget",
        available_budget_eur=55000,
    )
    _, err = submit_selection(
        "Ron Ben Ari",
        target_role="right-back",
        salary_eur=43000,
    )
    assert not err
    body, err2 = submit_selection(
        "Ron Ben Ari",
        target_role="right-back",
        salary_eur=43000,
    )
    assert not err2
    assert body["status"] == "PENDING_MANAGEMENT_APPROVAL"
    assert body["remaining_budget_eur"] == 12000
