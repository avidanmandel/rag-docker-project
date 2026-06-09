"""Root polished UI + Bedrock Agent integration tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"))

os.environ.setdefault("SCOUTMATCH_USE_LOCAL_STORE", "true")

import bedrock_agent_service as advisor  # noqa: E402
import database  # noqa: E402
from four_lambda_apply import FINAL_FOUR_LAMBDAS, FINAL_USER_FACING_FUNCTIONS  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    import config

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
    yield


def test_root_chat_uses_agent_path_when_extension_enabled(monkeypatch):
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    monkeypatch.setattr(flask_app, "recruitment_advisor_enabled", lambda: True)
    monkeypatch.setattr(
        flask_app,
        "invoke_recruitment_advisor",
        lambda question, session_id=None, pending_return_control=None, chat_context=None: {
            "enabled": True,
            "session_id": session_id or "agent-sess-1",
            "answer": "Grounded analyst response.",
            "refused": False,
            "generation_mode": "bedrock_agent",
            "metadata": {
                "tools_executed": ["PlanMatchTactics"],
                "documents_used": ["tactical_policy.md"],
            },
        },
    )
    client = flask_app.app.test_client()
    session = database.create_session()
    resp = client.post(
        f"/api/sessions/{session['id']}/messages",
        json={"content": "Coach brief: goalkeeper injured during training."},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["generation_mode"] == "bedrock_agent"
    assert payload["agent_metadata"]["tools_executed"] == ["PlanMatchTactics"]
    stored = database.get_session(session["id"])
    assert stored["bedrock_session_id"] == "agent-sess-1"


def test_same_agent_session_reused_across_messages(monkeypatch):
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    calls: list[str | None] = []

    def _invoke(question, session_id=None, pending_return_control=None, chat_context=None):
        calls.append(session_id)
        return {
            "enabled": True,
            "session_id": session_id or "agent-sess-abc",
            "answer": "ok",
            "refused": False,
            "generation_mode": "bedrock_agent",
            "metadata": {},
        }

    monkeypatch.setattr(flask_app, "recruitment_advisor_enabled", lambda: True)
    monkeypatch.setattr(flask_app, "invoke_recruitment_advisor", _invoke)
    client = flask_app.app.test_client()
    session = database.create_session()
    client.post(f"/api/sessions/{session['id']}/messages", json={"content": "first"})
    client.post(f"/api/sessions/{session['id']}/messages", json={"content": "second"})
    assert calls[0] is None
    assert calls[1] == "agent-sess-abc"


def test_new_conversation_gets_new_agent_session(monkeypatch):
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    monkeypatch.setattr(flask_app, "recruitment_advisor_enabled", lambda: True)
    monkeypatch.setattr(
        flask_app,
        "invoke_recruitment_advisor",
        lambda question, session_id=None, pending_return_control=None, chat_context=None: {
            "enabled": True,
            "session_id": session_id or "agent-new",
            "answer": "ok",
            "refused": False,
            "generation_mode": "bedrock_agent",
            "metadata": {},
        },
    )
    client = flask_app.app.test_client()
    s1 = database.create_session()
    s2 = database.create_session()
    client.post(f"/api/sessions/{s1['id']}/messages", json={"content": "one"})
    database.update_bedrock_session_id(s1["id"], "agent-old")
    client.post(f"/api/sessions/{s2['id']}/messages", json={"content": "two"})
    assert database.get_session(s1["id"])["bedrock_session_id"] == "agent-old"
    assert database.get_session(s2["id"])["bedrock_session_id"] == "agent-new"


def test_diagnostic_advisor_route_still_available():
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    client = flask_app.app.test_client()
    resp = client.get("/recruitment-advisor")
    assert resp.status_code == 200


def test_api_status_reports_agent_backend(monkeypatch):
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    monkeypatch.setattr(flask_app, "recruitment_advisor_enabled", lambda: True)
    client = flask_app.app.test_client()
    payload = client.get("/api/status").get_json()
    assert payload["agent_extension_enabled"] is True
    assert payload["chat_backend"] == "bedrock_agent"


def test_exactly_four_lambdas_and_functions():
    assert len(FINAL_FOUR_LAMBDAS) == 4
    assert len(FINAL_USER_FACING_FUNCTIONS) == 4


def test_coach_brief_goalkeeper_injury_plan_is_read_only():
    from lambda_test_isolation import reload_shared_football_modules

    reload_shared_football_modules()
    tactical = sys.modules["tactical_planner"]
    body = tactical.plan_match_tactics(
        opponent="",
        squad_context=(
            "Coach brief: Our starting goalkeeper was injured during training and will miss "
            "the next three matches. Which position should we prioritize?"
        ),
    )
    assert body["status"] == "TACTICAL_PLAN_UPDATED"
    assert body["urgent_squad_need"] == "Goalkeeper"
    assert body.get("read_only") is True


def test_confirmation_card_extracted_from_reprompt():
    events = [
        {
            "trace": {
                "trace": {
                    "orchestrationTrace": {
                        "invocationInput": {
                            "actionGroupInvocationInput": {
                                "function": "SubmitPlayerSelectionToManagement",
                                "parameters": [
                                    {"name": "candidate_name", "value": "Ron Ben Ari"},
                                    {"name": "target_role", "value": "right-back"},
                                    {"name": "salary_eur", "value": "43000"},
                                ],
                            }
                        },
                        "observation": {"repromptResponse": {"source": "ACTION_GROUP"}},
                    }
                }
            }
        }
    ]
    meta = advisor._extract_metadata(events, "Please confirm before submitting.")
    card = meta.get("confirmation_card")
    assert card is not None
    assert card["function"] == "SubmitPlayerSelectionToManagement"
    assert card["parameters"]["candidate_name"] == "Ron Ben Ari"


def test_confirmation_card_extracted_from_answer_text():
    answer = (
        "Before I reserve the budget, please confirm the following submission:\n"
        "- **Candidate:** Ron Ben Ari\n"
        "- **Target Role:** Right-Back\n"
        "- **Salary:** 43,000 EUR/year"
    )
    card = advisor._extract_confirmation_from_answer(answer)
    assert card is not None
    assert card["function"] == "SubmitPlayerSelectionToManagement"
    assert card["parameters"]["candidate"] == "Ron Ben Ari"


def test_agent_metadata_sanitizes_arns():
    text = advisor._sanitize_text("resource arn:aws:lambda:us-east-1:123456789012:function:test")
    assert "arn:aws" not in text
    assert "123456789012" not in text


def test_deploy_script_keeps_public_port_mapping():
    script = (ROOT / "scripts" / "deploy_recruitment_advisor_ec2.sh").read_text(encoding="utf-8")
    assert "0.0.0.0:80:5000" in script
    assert "127.0.0.1:5002:5000" in script
