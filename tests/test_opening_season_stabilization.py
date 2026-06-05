"""Regression tests for opening-season production stabilization pass."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "infra" / "scoutmatch_agent_extension" / "lambdas" / "shared_football"))
sys.path.insert(0, str(ROOT / "infra" / "scoutmatch_agent_extension" / "lambdas" / "common"))
sys.path.insert(0, str(ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"))

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ["SCOUTMATCH_DEMO_SEASON_ID"] = "opening-season-demo-v1"

import bedrock_agent_service as advisor  # noqa: E402
import database  # noqa: E402
from demo_roster import build_demo_starting_xi  # noqa: E402
from four_lambda_apply import FINAL_FOUR_LAMBDAS, FINAL_USER_FACING_FUNCTIONS  # noqa: E402
from lineup_store import finalize_lineup, get_current_lineup  # noqa: E402
from operations_store import clear_local_store, get_item, put_item  # noqa: E402
from player_selection import submit_selection  # noqa: E402
from sns_notification import publish_management_notification  # noqa: E402
from tactical_planner import plan_match_tactics  # noqa: E402
from validation import validate_starter_lineup  # noqa: E402
from write_confirmation import is_write_confirmed  # noqa: E402


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
    clear_local_store()
    yield
    clear_local_store()


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
