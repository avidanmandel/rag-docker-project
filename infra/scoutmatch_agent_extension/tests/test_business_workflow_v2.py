"""Business workflow v2 regression tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LAMBDAS = Path(__file__).resolve().parents[1] / "lambdas"
for p in (str(LAMBDAS / "common"), str(LAMBDAS / "shared_football"), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402

from four_lambda_apply import (  # noqa: E402
    FINAL_FOUR_LAMBDAS,
    FINAL_USER_FACING_FUNCTIONS,
    V2_USER_FACING_FUNCTIONS,
    is_business_workflow_v2_enabled,
)


def _load_lambda(folder: str):
    path = LAMBDAS / folder / "lambda_function.py"
    spec = importlib.util.spec_from_file_location(folder, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


_SHARED_OPS = LAMBDAS / "shared_football" / "operations_store.py"


def _shared_operations_store():
    spec = importlib.util.spec_from_file_location("operations_store", _SHARED_OPS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_RELOAD_MODULES = (
    "budget_ledger",
    "squad_context",
    "lineup_store",
    "lineup_svg",
    "visual_squad_board",
    "critical_decision",
    "transfer_out_review",
    "scouting_mission",
    "player_selection",
    "tactical_planner",
    "feature_flags",
    "ses_adapter",
    "google_calendar_adapter",
    "demo_roster",
)


@pytest.fixture(autouse=True)
def _isolated_operations_store():
    previous = sys.modules.get("operations_store")
    store = _shared_operations_store()
    sys.modules["operations_store"] = store
    store.clear_local_store()
    yield
    store.clear_local_store()
    if previous is not None:
        sys.modules["operations_store"] = previous
    else:
        sys.modules.pop("operations_store", None)


def _force_reload_shared_module(name: str) -> None:
    """Reload a shared module from disk with a canonical module name."""
    path = LAMBDAS / "shared_football" / f"{name}.py"
    if not path.exists():
        return
    sys.modules.pop(f"stab_{name}", None)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules[name] = module


def _reload_shared_modules() -> None:
    for name in _RELOAD_MODULES:
        _force_reload_shared_module(name)


@pytest.fixture(autouse=True)
def _v2_env():
    os.environ["SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED"] = "true"
    os.environ["SCOUTMATCH_EMAIL_MODE"] = "disabled"
    os.environ["SCOUTMATCH_CALENDAR_MODE"] = "ics_fallback"
    import importlib

    import four_lambda_apply

    importlib.reload(four_lambda_apply)
    yield
    os.environ.pop("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", None)


@pytest.fixture(autouse=True)
def _clear_store():
    from operations_store import clear_local_store

    clear_local_store()
    yield
    clear_local_store()


def test_v2_flag_enabled():
    assert is_business_workflow_v2_enabled()


def test_four_public_tools_v2():
    import importlib

    import four_lambda_apply

    importlib.reload(four_lambda_apply)
    assert len(four_lambda_apply.FINAL_FOUR_LAMBDAS) == 4
    assert set(four_lambda_apply.FINAL_USER_FACING_FUNCTIONS) == set(
        four_lambda_apply.V2_USER_FACING_FUNCTIONS
    )


def test_critical_decision_pre_confirm_and_confirm():
    mod = _load_lambda("submit_player_selection")
    prep = mod.lambda_handler(
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "actionGroup": "ScoutMatchCriticalDecisionActionsAvidan",
            "parameters": [
                {"name": "candidate_name", "value": "Ron Ben Ari"},
                {"name": "target_role", "value": "Right-back"},
                {"name": "salary_eur", "value": "43000"},
            ],
        },
        None,
    )
    body = _body(prep)
    assert body["status"] == "PENDING_CONFIRMATION"
    assert body["candidate_name"] == "Ron Ben Ari"

    deny = mod.lambda_handler(
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "confirmationState": "DENY",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
        None,
    )
    assert _body(deny)["status"] == "CANCELLED"

    confirm = mod.lambda_handler(
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "confirmationState": "CONFIRM",
            "parameters": [
                {"name": "candidate_name", "value": "Ron Ben Ari"},
                {"name": "target_role", "value": "Right-back"},
                {"name": "salary_eur", "value": "43000"},
            ],
        },
        None,
    )
    cbody = _body(confirm)
    assert cbody["status"] == "PENDING_MANAGEMENT_APPROVAL"
    assert cbody["reserved_amount_eur"] == 43000
    assert cbody["remaining_budget_eur"] == 57000

    again = mod.lambda_handler(
        {
            "function": "SubmitCriticalDecisionAndSendEmail",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
        None,
    )
    assert _body(again).get("idempotent") is True


def test_transfer_out_review_flow():
    mod = _load_lambda("plan_match_tactics")
    advisory = mod.lambda_handler(
        {
            "function": "OpenTransferOutReviewCase",
            "parameters": [{"name": "advisory_only", "value": "true"}, {"name": "player_name", "value": "Daniel Cohen"}],
        },
        None,
    )
    abody = _body(advisory)
    assert abody["status"] == "ADVISORY"
    assert abody["player_name"] == "Daniel Cohen"
    assert abody["estimated_budget_release_eur"] == 25000

    prep = mod.lambda_handler(
        {
            "function": "OpenTransferOutReviewCase",
            "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
        },
        None,
    )
    assert _body(prep)["status"] == "PENDING_CONFIRMATION"

    confirm = mod.lambda_handler(
        {
            "function": "OpenTransferOutReviewCase",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
        },
        None,
    )
    cbody = _body(confirm)
    assert cbody["status"] == "PENDING_TECHNICAL_DIRECTOR_REVIEW"
    assert cbody["estimated_budget_release_eur"] == 25000

    from budget_ledger import available_budget_from_context, ensure_demo_context

    ensure_demo_context()
    available, _ = available_budget_from_context()
    assert available == 100000


def test_scouting_mission_create_and_review():
    mod = _load_lambda("finalize_current_lineup")
    prep = mod.lambda_handler(
        {
            "function": "CreateAndReviewScoutingMission",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
        None,
    )
    assert _body(prep)["status"] == "PENDING_CONFIRMATION"

    confirm = mod.lambda_handler(
        {
            "function": "CreateAndReviewScoutingMission",
            "confirmationState": "CONFIRM",
            "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
        },
        None,
    )
    body = _body(confirm)
    assert body["status"] == "PENDING_SCOUT_OBSERVATION"
    assert body["calendar_label"]
    assert body.get("calendar_invite_key")

    review = mod.lambda_handler(
        {
            "function": "CreateAndReviewScoutingMission",
            "parameters": [
                {"name": "candidate_name", "value": "Ron Ben Ari"},
                {"name": "mission_mode", "value": "REVIEW_COMPLETED_MISSION"},
            ],
        },
        None,
    )
    rbody = _body(review)
    assert rbody["status"] == "READY_FOR_RECRUITMENT_REVIEW"
    assert "Demo replay" in rbody["report_label"]
    assert rbody["report_type"] == "synthetic_demo_replay"


def _snapshot_shared_modules() -> dict[str, object | None]:
    names = list(_RELOAD_MODULES) + ["operations_store"]
    return {name: sys.modules.get(name) for name in names}


def _restore_shared_modules(snapshot: dict[str, object | None]) -> None:
    for name, module in snapshot.items():
        if module is not None:
            sys.modules[name] = module
        else:
            sys.modules.pop(name, None)


def test_visual_squad_board_save_and_render():
    from budget_ledger import ensure_demo_context
    from operations_store import clear_local_store

    snapshot = _snapshot_shared_modules()
    try:
        store = _shared_operations_store()
        sys.modules["operations_store"] = store
        _reload_shared_modules()
        clear_local_store()
        ensure_demo_context(budget_eur=100_000)
        submit = _load_lambda("submit_player_selection")
        submit.lambda_handler(
            {
                "function": "SubmitCriticalDecisionAndSendEmail",
                "confirmationState": "CONFIRM",
                "parameters": [{"name": "candidate_name", "value": "Ron Ben Ari"}],
            },
            None,
        )
        transfer = _load_lambda("plan_match_tactics")
        transfer.lambda_handler(
            {
                "function": "OpenTransferOutReviewCase",
                "confirmationState": "CONFIRM",
                "parameters": [{"name": "player_name", "value": "Daniel Cohen"}],
            },
            None,
        )
        board = _load_lambda("generate_lineup_board")
        prep = board.lambda_handler(
            {
                "function": "GenerateVisualSquadAndLineupBoard",
                "parameters": [{"name": "board_mode", "value": "SAVE_AND_RENDER"}, {"name": "demo_lineup", "value": "true"}],
            },
            None,
        )
        assert _body(prep)["status"] == "PENDING_CONFIRMATION"

        save = board.lambda_handler(
            {
                "function": "GenerateVisualSquadAndLineupBoard",
                "confirmationState": "CONFIRM",
                "parameters": [{"name": "board_mode", "value": "SAVE_AND_RENDER"}, {"name": "demo_lineup", "value": "true"}],
            },
            None,
        )
        sbody = _body(save)
        assert sbody["status"] == "PENDING_HEAD_COACH_REVIEW", sbody.get("message", sbody)
        assert sbody.get("image_route")

        render = board.lambda_handler(
            {
                "function": "GenerateVisualSquadAndLineupBoard",
                "parameters": [{"name": "board_mode", "value": "RENDER_CURRENT"}],
            },
            None,
        )
        rbody = _body(render)
        assert rbody["status"] == "LINEUP_BOARD_GENERATED"
        assert rbody.get("remaining_confirmed_budget_eur") == 57000
    finally:
        _restore_shared_modules(snapshot)


def test_ics_generation():
    from ics_calendar import build_ics_invite

    ics = build_ics_invite(
        uid="mission-test",
        title="ScoutMatch AI — Live Observation: Ron Ben Ari",
        description="Final scouting observation",
        start_iso="2026-06-20T17:00:00+00:00",
    )
    assert "BEGIN:VCALENDAR" in ics
    assert "VEVENT" in ics


def test_ses_disabled_fallback():
    from ses_adapter import send_review_email

    result = send_review_email({"candidate_name": "Ron Ben Ari", "status": "PENDING_MANAGEMENT_APPROVAL"})
    assert result["sent"] is False
    assert "saved for management review" in result["user_message"]
