import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ["SCOUTMATCH_WORKFLOW_INPROCESS"] = "true"

_OPS = Path(__file__).resolve().parents[1] / "lambdas" / "football_operations"
_COMMON = _OPS.parent / "common"
for path in (str(_COMMON), str(_OPS)):
    if path not in sys.path:
        sys.path.insert(0, path)

_spec = importlib.util.spec_from_file_location("football_ops_lambda", _OPS / "lambda_function.py")
ops = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ops)

from operations_store import clear_local_store  # noqa: E402


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
    clear_local_store()
    yield
    clear_local_store()


DEMO_XI = (
    "Avi Cohen:GK;Michael Ross:RB;Yossi Bar:CB;Daniel Levy:CB;Tal Amar:LB;"
    "Noam Sharon:CM;Ido Katz:CM;Eran Blum:CM;Lior Dan:RW;Amit Peretz:ST;Guy Navon:LW"
)


def test_update_squad_context_saved():
    body = _body(
        ops.lambda_handler(
            _event(
                "UpdateSquadPlanningContext",
                {
                    "opponent": "Barcelona",
                    "preferred_formation": "4-3-3",
                    "priority_positions": "RB",
                    "strong_positions": "attack",
                    "available_budget_eur": 55000,
                },
            ),
            None,
        )
    )
    assert body["status"] == "SAVED"
    assert body["context"]["opponent"] == "Barcelona"
    assert "planning_context_id" in body["context"]


def test_update_context_missing_fields():
    body = _body(ops.lambda_handler(_event("UpdateSquadPlanningContext", {"opponent": "Barcelona"}), None))
    assert body["status"] == "NEEDS_CLARIFICATION"


def test_submit_selection_deny_no_write():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {
                "opponent": "Barcelona",
                "preferred_formation": "4-3-3",
                "available_budget_eur": 55000,
            },
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}),
            None,
        )
    )
    assert body["status"] == "PENDING_CONFIRMATION"


def test_submit_selection_confirm_reserves_budget():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {
                "opponent": "Barcelona",
                "preferred_formation": "4-3-3",
                "available_budget_eur": 55000,
            },
        ),
        None,
    )
    first = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, confirmed=True),
            None,
        )
    )
    assert first["status"] == "RESERVED"
    assert first["remaining_budget_eur"] == 12000
    second = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, confirmed=True),
            None,
        )
    )
    assert second["status"] == "ALREADY_RESERVED"
    assert second["idempotent"] is True


def test_unknown_candidate_rejected():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Unknown Player"}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "FAILURE"


def test_finalize_lineup_requires_confirmation():
    body = _body(
        ops.lambda_handler(
            _event("FinalizeCurrentLineup", {"formation": "4-3-3", "starting_xi": DEMO_XI}),
            None,
        )
    )
    assert body["status"] == "PENDING_CONFIRMATION"


def test_finalize_lineup_valid_433():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    body = _body(
        ops.lambda_handler(
            _event("FinalizeCurrentLineup", {"formation": "4-3-3", "starting_xi": DEMO_XI}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "SAVED"
    assert len(body["lineup"]["starting_xi"]) == 11


def test_finalize_lineup_duplicate_rejected():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    dup = "Avi Cohen:GK;Avi Cohen:RB;Yossi Bar:CB;Daniel Levy:CB;Tal Amar:LB;Noam Sharon:CM;Ido Katz:CM;Eran Blum:CM;Lior Dan:RW;Amit Peretz:ST;Guy Navon:LW"
    body = _body(
        ops.lambda_handler(
            _event("FinalizeCurrentLineup", {"starting_xi": dup}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "REJECTED"


def test_generate_lineup_board_svg():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 55000},
        ),
        None,
    )
    xi = (
        "Avi Cohen:GK;Ron Ben Ari:RB;Yossi Bar:CB;Michael Ross:CB;Tal Amar:LB;"
        "Noam Sharon:CM;Ido Katz:CM;Eran Blum:CM;Lior Dan:RW;Amit Peretz:ST;Guy Navon:LW"
    )
    ops.lambda_handler(
        _event(
            "SubmitPlayerSelectionToManagement",
            {"candidate_name": "Ron Ben Ari"},
            confirmed=True,
        ),
        None,
    )
    ops.lambda_handler(_event("FinalizeCurrentLineup", {"starting_xi": xi}, confirmed=True), None)
    body = _body(ops.lambda_handler(_event("GenerateCurrentLineupBoard", {}), None))
    assert body["status"] == "RENDERED"
    assert body["image_route"] == "/api/recruitment-advisor/lineups/current/image"
    assert "scoutmatch/football-operations/lineups/" in body["object_key"]
    from lineup_svg import get_local_svg

    svg = get_local_svg("current")
    assert svg and "<svg" in svg
    assert "Barcelona" in svg
    assert "4-3-3" in svg
    assert "PENDING APPROVAL" in svg
    assert svg.count("<circle") >= 11


def test_sns_payload_has_no_email():
    from sns_notification import build_management_message

    msg = build_management_message(
        {
            "candidate_name": "Ron Ben Ari",
            "target_role": "right-back",
            "salary_request_eur": 43000,
            "reservation_status": "RESERVED_PENDING_APPROVAL",
            "approval_status": "PENDING_MANAGEMENT_APPROVAL",
        },
        "PASS",
    )
    assert "@" not in msg
    assert "Ron Ben Ari" in msg


def test_demo_lineup_finalize_ron_right_back():
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
    body = _body(
        ops.lambda_handler(
            _event("FinalizeCurrentLineup", {"demo_lineup": "true", "formation": "4-3-3"}, confirmed=True),
            None,
        )
    )
    assert body["status"] == "SAVED"
    ron = next(p for p in body["lineup"]["starting_xi"] if p["name"] == "Ron Ben Ari")
    assert ron["position"] == "RB"
    assert ron["status"] == "PENDING_MANAGEMENT_APPROVAL"


def test_analyze_depth_internal():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {
                "opponent": "Barcelona",
                "preferred_formation": "4-3-3",
                "priority_positions": "RB",
                "available_budget_eur": 55000,
            },
        ),
        None,
    )
    body = _body(ops.lambda_handler(_event("AnalyzeSquadDepthGaps", {}), None))
    assert body["status"] == "OK"
    assert "gaps" in body["analysis"]
