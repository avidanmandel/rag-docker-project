"""Regression tests for eleven-player lineup board SVG and budget display."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_OPS = ROOT / "infra/scoutmatch_agent_extension/lambdas/football_operations"
os.environ.setdefault("SCOUTMATCH_USE_LOCAL_STORE", "true")
os.environ.setdefault("SCOUTMATCH_WORKFLOW_INPROCESS", "true")

for path in (str(_OPS.parent / "common"), str(_OPS)):
    if path not in sys.path:
        sys.path.insert(0, path)

_spec = importlib.util.spec_from_file_location("football_ops_lambda", _OPS / "lambda_function.py")
ops = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ops)

from operations_store import clear_local_store, list_by_prefix  # noqa: E402

import bedrock_agent_service as advisor  # noqa: E402


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def _event(function, params, confirmed=False):
    return {
        "function": function,
        "actionGroup": "ScoutMatchFootballOperationsActionsAvidan",
        "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
        "sessionAttributes": {"write_confirmed": "true"} if confirmed else {},
    }


def _player_marker_coords(svg: str) -> list[tuple[str, str]]:
    return re.findall(r'<circle cx="(\d+)" cy="(\d+)" r="22"', svg)


def _player_marker_names(svg: str) -> list[str]:
    return re.findall(r'font-size="12"[^>]*>([^<]+)</text>', svg)


@pytest.fixture(autouse=True)
def reset_store():
    clear_local_store()
    yield
    clear_local_store()


def _seed_demo_flow(*, confirm_ron: bool = True) -> dict:
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 100000},
        ),
        None,
    )
    selection = {}
    if confirm_ron:
        selection = _body(
            ops.lambda_handler(
                _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, True),
                None,
            )
        )
    xi = (
        "Avi Cohen:GK;Ron Ben Ari:RB;Yossi Bar:CB;Michael Ross:CB;Tal Amar:LB;"
        "Noam Sharon:CM;Ido Katz:CM;Eran Blum:CM;Lior Dan:RW;Amit Peretz:ST;Guy Navon:LW"
    )
    lineup = _body(ops.lambda_handler(_event("FinalizeCurrentLineup", {"starting_xi": xi}, True), None))
    board = _body(ops.lambda_handler(_event("GenerateCurrentLineupBoard", {}), None))
    import lineup_svg

    svg = lineup_svg.get_local_svg("current") or ""
    return {"selection": selection, "lineup": lineup, "board": board, "svg": svg}


def test_saved_lineup_contains_exactly_eleven_players():
    result = _seed_demo_flow()
    assert len(result["lineup"]["lineup"]["starting_xi"]) == 11
    assert result["lineup"]["status"] == "SAVED"
    assert result["board"]["player_count"] == 11


def test_svg_contains_eleven_distinct_player_markers():
    result = _seed_demo_flow()
    svg = result["svg"]
    coords = _player_marker_coords(svg)
    assert len(coords) == 11
    assert len(set(coords)) == 11


def test_svg_marker_names_are_distinct_and_readable():
    result = _seed_demo_flow()
    names = _player_marker_names(result["svg"])
    assert len(names) == 11
    assert len(set(names)) == 11
    assert "Ari" in names
    assert "Cohen" in names


def test_ron_ben_ari_visible_at_right_back_with_pending_highlight():
    result = _seed_demo_flow()
    svg = result["svg"]
    assert "Ari" in svg
    assert "PENDING APPROVAL" in svg
    assert 'fill="#f4c542"' in svg
    rb_coords = re.findall(
        r'<circle cx="(\d+)" cy="(\d+)" r="22" fill="#f4c542"[^/]*/>\s*'
        r'<text x="\1" y="[^"]*"[^>]*>Ari</text>\s*'
        r'<text x="\1" y="[^"]*"[^>]*>RB</text>',
        svg,
    )
    assert rb_coords


def test_budget_before_confirmation_is_full_demo_scope():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 100000},
        ),
        None,
    )
    board = _body(ops.lambda_handler(_event("GenerateCurrentLineupBoard", {}), None))
    assert board["status"] == "NOT_FOUND"


def test_budget_after_ron_confirmation_is_fifty_seven_thousand():
    result = _seed_demo_flow()
    assert result["selection"]["reserved_amount_eur"] == 43000
    assert result["selection"]["remaining_budget_eur"] == 57000
    assert result["board"]["remaining_budget_eur"] == 57000


def test_repeated_confirmation_is_idempotent_for_budget():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 100000},
        ),
        None,
    )
    first = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, True),
            None,
        )
    )
    second = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, True),
            None,
        )
    )
    assert second.get("idempotent") is True
    assert second["remaining_budget_eur"] == first["remaining_budget_eur"] == 57000
    reservations = [e for e in list_by_prefix("budget_ledger#") if e.get("entry_type") == "RESERVATION"]
    assert len(reservations) == 1


def test_legacy_ledger_without_context_uses_matching_selection_scope():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 100000},
        ),
        None,
    )
    selection = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, True),
            None,
        )
    )
    from operations_store import list_by_prefix, put_item

    for entry in list_by_prefix("budget_ledger#"):
        if entry.get("entry_type") == "RESERVATION":
            legacy = {
                k: v
                for k, v in entry.items()
                if k not in {"entity_key", "item_type", "updated_at", "planning_context_id"}
            }
            put_item(entity_key=entry["entity_key"], item_type="BUDGET_LEDGER", payload=legacy)
            break
    xi = (
        "Avi Cohen:GK;Ron Ben Ari:RB;Yossi Bar:CB;Michael Ross:CB;Tal Amar:LB;"
        "Noam Sharon:CM;Ido Katz:CM;Eran Blum:CM;Lior Dan:RW;Amit Peretz:ST;Guy Navon:LW"
    )
    ops.lambda_handler(_event("FinalizeCurrentLineup", {"starting_xi": xi}, True), None)
    board = _body(ops.lambda_handler(_event("GenerateCurrentLineupBoard", {}), None))
    assert selection["remaining_budget_eur"] == 57000
    assert board["remaining_budget_eur"] == 57000


def test_deny_does_not_reserve_budget():
    ops.lambda_handler(
        _event(
            "UpdateSquadPlanningContext",
            {"opponent": "Barcelona", "preferred_formation": "4-3-3", "available_budget_eur": 100000},
        ),
        None,
    )
    deny = _body(
        ops.lambda_handler(
            _event("SubmitPlayerSelectionToManagement", {"candidate_name": "Ron Ben Ari"}, False),
            None,
        )
    )
    assert deny["status"] == "PENDING_CONFIRMATION"
    reservations = [e for e in list_by_prefix("budget_ledger#") if e.get("entry_type") == "RESERVATION"]
    assert reservations == []


def test_clean_user_facing_lineup_status_text():
    text = advisor._format_lineup_success(
        {"formation": "4-3-3", "starting_players": 11, "status": "PENDING_HEAD_COACH_REVIEW"}
    )
    assert "Pending head-coach review" in text
    assert "PENDING_HEAD_COACH_REVIEW" not in text


def test_lineup_board_container_css_is_responsive():
    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
    block = css.split(".lineup-board-card__image")[1].split("}", 1)[0]
    assert "max-width: 100%" in block
    assert "object-fit: contain" in block


def test_frontend_hides_raw_proxy_route_and_internal_status_enums():
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    assert "PENDING_HEAD_COACH_REVIEW" in js
    assert "Pending head-coach review" in js
    assert "View:\\s*\\/api\\/recruitment-advisor" in js
