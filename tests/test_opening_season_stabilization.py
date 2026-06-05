"""Regression tests for opening-season production stabilization pass."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "infra" / "scoutmatch_agent_extension" / "lambdas" / "shared_football"
COMMON = ROOT / "infra" / "scoutmatch_agent_extension" / "lambdas" / "common"
SCRIPTS = ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ["SCOUTMATCH_DEMO_SEASON_ID"] = "opening-season-demo-v1"

import importlib.util

import bedrock_agent_service as advisor  # noqa: E402
import database  # noqa: E402


_STAB_PREFIX = "stab_"
_STAB_ALIASES = (
    "operations_store",
    "tactical_planner",
    "lineup_store",
    "player_selection",
    "budget_ledger",
    "budget_rules",
    "validation",
    "demo_roster",
    "sns_notification",
)


def _ensure_shared_paths() -> None:
    for path in (str(SHARED), str(COMMON), str(SCRIPTS), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _purge_stab_modules() -> None:
    for name in _STAB_ALIASES:
        sys.modules.pop(f"{_STAB_PREFIX}{name}", None)
    for name in _STAB_ALIASES:
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", "") or ""
        if mod is not None and "shared_football" in str(mod_file).replace("\\", "/"):
            sys.modules.pop(name, None)


def _load_stab(internal_name: str, filename: str):
    mod_key = f"{_STAB_PREFIX}{internal_name}"
    spec = importlib.util.spec_from_file_location(mod_key, SHARED / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[mod_key] = module
    sys.modules[internal_name] = module
    spec.loader.exec_module(module)
    return module


def _bind_shared_modules() -> None:
    global clear_local_store, get_item, put_item, plan_match_tactics
    global finalize_lineup, get_current_lineup, submit_selection
    global publish_management_notification, build_demo_starting_xi
    global validate_starter_lineup, FINAL_FOUR_LAMBDAS, FINAL_USER_FACING_FUNCTIONS
    global is_write_confirmed

    _purge_stab_modules()
    _ensure_shared_paths()

    _ops = _load_stab("operations_store", "operations_store.py")
    _load_stab("budget_rules", "budget_rules.py")
    _load_stab("budget_ledger", "budget_ledger.py")
    _validation = _load_stab("validation", "validation.py")
    _sns = _load_stab("sns_notification", "sns_notification.py")
    _demo = _load_stab("demo_roster", "demo_roster.py")
    _load_stab("squad_context", "squad_context.py")
    _tactical = _load_stab("tactical_planner", "tactical_planner.py")
    _lineup = _load_stab("lineup_store", "lineup_store.py")
    _selection = _load_stab("player_selection", "player_selection.py")

    for name in _STAB_ALIASES:
        sys.modules.pop(name, None)

    clear_local_store = _ops.clear_local_store
    get_item = _ops.get_item
    put_item = _ops.put_item
    plan_match_tactics = _tactical.plan_match_tactics
    finalize_lineup = _lineup.finalize_lineup
    get_current_lineup = _lineup.get_current_lineup
    submit_selection = _selection.submit_selection
    publish_management_notification = _sns.publish_management_notification
    build_demo_starting_xi = _demo.build_demo_starting_xi
    validate_starter_lineup = _validation.validate_starter_lineup

    _spec = importlib.util.spec_from_file_location("four_lambda_apply", SCRIPTS / "four_lambda_apply.py")
    _four = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_four)
    FINAL_FOUR_LAMBDAS = _four.FINAL_FOUR_LAMBDAS
    FINAL_USER_FACING_FUNCTIONS = _four.FINAL_USER_FACING_FUNCTIONS

    _wc_spec = importlib.util.spec_from_file_location("write_confirmation", COMMON / "write_confirmation.py")
    _wc = importlib.util.module_from_spec(_wc_spec)
    assert _wc_spec.loader is not None
    _wc_spec.loader.exec_module(_wc)
    is_write_confirmed = _wc.is_write_confirmed


_bind_shared_modules()


_SHARED_NAMES = _STAB_ALIASES + ("squad_context",)


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    import config

    monkeypatch.setenv("SCOUTMATCH_USE_LOCAL_STORE", "true")
    monkeypatch.setenv("SCOUTMATCH_DEMO_SEASON_ID", "opening-season-demo-v1")
    db_path = tmp_path / "chat.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    if hasattr(database._local, "conn"):
        try:
            database.get_connection().close()
        except Exception:
            pass
        del database._local.conn
    database.init_db()
    _bind_shared_modules()
    clear_local_store()
    yield
    clear_local_store()
    _purge_stab_modules()


def _seed_planning_context() -> None:
    plan_match_tactics(
        opponent="Maccabi Haifa",
        squad_context="Right-back depth weak.",
        available_budget_eur=100000,
    )


def test_guardrail_paraphrase_maps_rb_comparison_prompt():
    original = (
        "Compare the right-back candidates within our recruitment budget. "
        "Include Ron Ben Ari and the other documented right-back options."
    )
    safe = advisor._guardrail_safe_prompt(original)
    assert "Tal Cohen" in safe
    assert "other documented" not in safe


def test_sns_publish_does_not_raise_without_topic_arn():
    result = publish_management_notification(
        {
            "candidate_name": "Ron Ben Ari",
            "target_role": "right-back",
            "salary_request_eur": 43000,
            "reservation_status": "RESERVED_PENDING_APPROVAL",
            "approval_status": "PENDING_MANAGEMENT_APPROVAL",
        },
        "PASS",
    )
    assert result.get("published") in {False, True}
    assert "mode" in result or "message_preview" in result


def test_selection_confirm_reserves_budget_once():
    _seed_planning_context()
    event = {
        "function": "SubmitPlayerSelectionToManagement",
        "confirmationState": "CONFIRM",
    }
    assert is_write_confirmed(event)
    body, err = submit_selection(
        "Ron Ben Ari",
        target_role="right-back",
        salary_eur=43000,
        selection_reason="aggressive right-back",
    )
    assert err == ""
    assert body["status"] == "PENDING_MANAGEMENT_APPROVAL"
    assert body["remaining_budget_eur"] == 57000
    repeat, err2 = submit_selection("Ron Ben Ari", target_role="right-back", salary_eur=43000)
    assert err2 == ""
    assert repeat.get("idempotent") is True


def test_selection_deny_does_not_write():
    _seed_planning_context()
    assert not is_write_confirmed({"confirmationState": "DENY"})
    assert get_item("player_selection#ron ben ari") is None


def test_demo_lineup_allows_ron_ben_ari_at_right_back():
    _seed_planning_context()
    starters = build_demo_starting_xi(ron_at_right_back=True)
    ok, err = validate_starter_lineup(
        starters,
        allowed_external=frozenset({"ron ben ari"}),
    )
    assert ok, err
    record, err = finalize_lineup(
        {"formation": "4-3-3", "demo_lineup": "true", "opponent": "Maccabi Haifa"}
    )
    assert err == ""
    assert record["status"] == "PENDING_HEAD_COACH_REVIEW"
    assert len(record["starting_xi"]) == 11


def test_lineup_scoped_to_active_demo_season_only():
    put_item(
        entity_key="lineup#current",
        item_type="LINEUP",
        payload={
            "demo_season_id": "legacy-demo-season",
            "formation": "4-4-2",
            "starting_xi": [{"name": "Avi Cohen", "position": "GK"}],
        },
    )
    assert get_current_lineup() is None


def test_format_selection_success_hides_internal_ids():
    text = advisor._format_selection_success(
        {"selected_player": "Ron Ben Ari", "remaining_budget_eur": 57000}
    )
    assert "PENDING_MANAGEMENT_APPROVAL" in text
    assert "ctx-" not in text


def test_sanitize_text_removes_sns_wording():
    text = advisor._sanitize_text("Notify management via SNS about planning_context_id ctx-abc123")
    assert "SNS" not in text
    assert "planning context" in text.lower()


def test_confirmation_card_cleared_flag_on_confirm_failure():
    with patch.object(advisor, "is_enabled", return_value=True), patch.object(
        advisor, "_invoke_agent_once", side_effect=RuntimeError("boom")
    ):
        result = advisor.invoke_agent("Confirm", session_id="sess-1")
    assert result.get("clear_pending_action") is True
    assert result["session_id"] != "sess-1"


def test_exactly_four_tools_and_lambdas_preserved():
    assert len(FINAL_USER_FACING_FUNCTIONS) == 4
    assert len(FINAL_FOUR_LAMBDAS) == 4


def test_homepage_has_collapsed_sidebar_groups():
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    resp = flask_app.app.test_client().get("/")
    html = resp.get_data(as_text=True)
    assert "sidebar-group" in html
    assert "Club Knowledge" in html
    assert "Recruitment Candidate Pool" in html
    assert "AWS Bedrock KB connected" not in html


def test_landing_layout_css_prevents_card_and_image_clipping():
    css = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert "Landing layout stabilization" in css
    assert ".messages--landing .home-hero .suggestions" in css
    assert "object-fit: contain" in css
    assert "max-height: 132px" not in css.split("Opening-season stabilization")[-1]


def test_opening_season_counts_api():
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    with patch.object(flask_app, "recruitment_advisor_enabled", return_value=True):
        with patch.object(flask_app.engine, "ready", True):
            with patch.object(flask_app.engine, "status", "ready"):
                with patch.object(flask_app, "_is_aws_kb_mode", return_value=True):
                    with patch.object(flask_app.config, "validate_aws_config", return_value=[]):
                        status = flask_app.app.test_client().get("/api/status").get_json()
                        workspace = flask_app.app.test_client().get(
                            "/api/opening-season/workspace"
                        ).get_json()
    assert status["club_player_count"] == 15
    assert status["candidate_pool_count"] == 8
    assert workspace["club_player_count"] == 15
    assert workspace["candidate_pool_count"] == 8
