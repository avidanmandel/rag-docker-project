"""Final pre-apply hardening: demo roster, budget helper IAM, lineup demo flow."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"

EXT = Path(__file__).resolve().parents[1]
ROOT = EXT.parents[1]
OPS = EXT / "lambdas" / "football_operations"
_COMMON = EXT / "lambdas" / "common"
_SCRIPTS = EXT / "scripts"
_DEMO_JSON = EXT / "demo_data" / "scoutmatch_demo_roster.json"
_DEPLOY = EXT / "scripts" / "deploy_scoutmatch_extension.py"

for path in (str(_COMMON), str(OPS), str(_SCRIPTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from lambda_test_isolation import reload_football_operations_lambda  # noqa: E402
from football_operations_apply import (  # noqa: E402
    ACTIVE_INTERNAL_HELPERS_AT_RUNTIME,
    BUDGET_HELPER_LAMBDA_NAME,
    NATIVE_AGENT_FUNCTIONS_SIMPLIFIED,
    ROLLBACK_ONLY_INTERNAL_HELPERS,
)

ops = None


def _demo():
    return sys.modules["demo_roster"]


def _store():
    return sys.modules["operations_store"]


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def _event(function, params, confirmed=False):
    return {
        "function": function,
        "actionGroup": "ScoutMatchFootballOperationsActionsAvidan",
        "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
        "sessionAttributes": {"write_confirmed": "true"} if confirmed else {},
    }


@pytest.fixture(autouse=True)
def reset_store():
    global ops
    ops, store = reload_football_operations_lambda()
    store.clear_local_store()
    yield
    store.clear_local_store()


def test_demo_roster_json_has_eleven_sanitized_players():
    data = json.loads(_DEMO_JSON.read_text(encoding="utf-8"))
    assert data["record_scope"] == "DEMO"
    assert data["formation"] == "4-3-3"
    assert len(data["players"]) == 11
    roles = {p["role_slot"] for p in data["players"]}
    assert roles == {
        "goalkeeper",
        "right-back",
        "center-back",
        "left-back",
        "midfielder",
        "right-winger",
        "striker",
        "left-winger",
    }
    assert data["demo_right_back_candidate"]["name"] == "Ron Ben Ari"


def test_demo_roster_valid_433_role_counts():
    data = _demo().load_demo_roster_from_file()
    positions = [p["position"] for p in data["players"]]
    assert positions.count("GK") == 1
    assert positions.count("RB") == 1
    assert positions.count("CB") == 2
    assert positions.count("LB") == 1
    assert positions.count("CM") == 3
    assert positions.count("RW") == 1
    assert positions.count("ST") == 1
    assert positions.count("LW") == 1


def test_build_demo_starting_xi_puts_ron_at_right_back():
    starters = _demo().build_demo_starting_xi(ron_at_right_back=True)
    assert len(starters) == 11
    rb = [p for p in starters if p["position"] == "RB"]
    assert len(rb) == 1
    assert rb[0]["name"] == "Ron Ben Ari"


def test_demo_seed_idempotent_and_skips_non_demo():
    first = _demo().seed_demo_roster_idempotent(apply=True)
    assert first["status"] == "SEEDED"
    second = _demo().seed_demo_roster_idempotent(apply=True)
    assert second["status"] == "ALREADY_SEEDED"
    _store().put_item(
        entity_key=_demo().DEMO_ROSTER_ENTITY_KEY,
        item_type="PRODUCTION_ROSTER",
        payload={"record_scope": "PRODUCTION", "players": []},
    )
    third = _demo().seed_demo_roster_idempotent(apply=True)
    assert third["status"] == "SKIPPED"
    assert third["reason"] == "non_demo_record_present"


def test_demo_lineup_finalize_with_ron_and_pending_badge():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    ops.lambda_handler(
        _event(
            "SubmitPlayerSelectionToManagement",
            {"candidate_name": "Ron Ben Ari"},
            confirmed=True,
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("FinalizeCurrentLineup", {"demo_lineup": "true", "formation": "4-3-3"}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "SAVED"
    lineup = body["lineup"]["starting_xi"]
    assert len(lineup) == 11
    ron = next(p for p in lineup if p["name"] == "Ron Ben Ari")
    assert ron["position"] == "RB"
    assert ron["status"] == "PENDING_MANAGEMENT_APPROVAL"


def test_non_demo_incomplete_lineup_rejected():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("FinalizeCurrentLineup", {"starting_xi": "Avi Cohen:GK"}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "REJECTED"
    assert "11" in body["message"]


def test_demo_lineup_svg_contains_ron_rb_pending_and_no_opponent_lineup():
    _demo().seed_demo_roster_idempotent(apply=True)
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    ops.lambda_handler(
        _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, confirmed=True),
        None,
    )
    ops.lambda_handler(
        _event("FinalizeCurrentLineup", {"demo_lineup": "true"}, confirmed=True),
        None,
    )
    board = _body(ops.lambda_handler(_event("GenerateCurrentLineupBoard", {}), None))
    assert board["status"] == "RENDERED"
    import lineup_svg as football_lineup_svg

    svg = football_lineup_svg.get_local_svg("current")
    import re

    assert svg and len(re.findall(r'<circle cx="\d+" cy="\d+" r="22"', svg)) == 11
    assert "Ron Ben Ari" in svg or "Ben Ari" in svg or "Ari" in svg
    assert "PENDING APPROVAL" in svg
    assert "Barcelona" in svg
    assert "opponent_xi" not in svg.lower()


def test_budget_helper_pass_path():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "RESERVED"
    assert body["budget_decision"] in {"PASS", "NEEDS_EXCEPTION"}


def test_budget_helper_fail_path_no_reservation():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 1000},
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "REJECTED"
    assert _store().get_item("player_selection#ron ben ari") is None


def _load_football_operations_player_selection():
    return sys.modules["player_selection"]


def test_budget_helper_invoke_failure_safe_no_write_no_sns():
    football_player_selection = _load_football_operations_player_selection()

    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    os.environ.pop("SCOUTMATCH_WORKFLOW_INPROCESS", None)
    error = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "denied"}}, "Invoke")
    with patch("boto3.client") as mock_client:
        mock_client.return_value.invoke.side_effect = error
        body, err = football_player_selection.submit_selection("Ron Ben Ari")
    os.environ["SCOUTMATCH_WORKFLOW_INPROCESS"] = "true"
    assert not err
    assert body["status"] == "REJECTED"
    assert "Budget helper" in body["message"] or "unavailable" in body["message"].lower()
    assert _store().get_item("player_selection#ron ben ari") is None


def test_deploy_plan_scopes_budget_helper_invoke():
    text = _DEPLOY.read_text(encoding="utf-8")
    assert "ScoutMatchBudgetImpactAvidan" in text
    assert "lambda:InvokeFunction" in text
    assert "ScoutMatchNativeToolsAvidan" in text or "NATIVE_TOOLS_ROLE" in text


def test_exactly_four_agent_facing_tools():
    assert len(NATIVE_AGENT_FUNCTIONS_SIMPLIFIED) == 4
    assert "CalculateBudgetImpact" not in NATIVE_AGENT_FUNCTIONS_SIMPLIFIED


def test_active_vs_rollback_internal_helpers():
    assert "CalculateBudgetImpact" in ACTIVE_INTERNAL_HELPERS_AT_RUNTIME
    assert "EvaluateRightBackFit" in ROLLBACK_ONLY_INTERNAL_HELPERS
    assert BUDGET_HELPER_LAMBDA_NAME == "ScoutMatchBudgetImpactAvidan"


def test_demo_starting_xi_string_matches_eleven_players():
    xi = _demo().demo_starting_xi_string(ron_at_right_back=True)
    assert len(xi.split(";")) == 11
    assert "Ron Ben Ari:RB" in xi
