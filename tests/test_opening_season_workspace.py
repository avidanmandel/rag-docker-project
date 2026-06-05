"""Opening-season workspace dataset and UI contract tests."""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import opening_season_workspace as ws  # noqa: E402


def _load_squad_rows() -> list[dict]:
    path = ws.DATASET_ROOT / "current_club_squad.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_opening_season_dataset_files_exist():
    files = ws.dataset_files()
    assert len(files) >= 16


def test_current_squad_has_15_players():
    rows = _load_squad_rows()
    assert len(rows) == ws.CLUB_PLAYER_COUNT == 15


def test_likely_starters_and_rotation():
    rows = _load_squad_rows()
    starters = [r for r in rows if r["squad_role"] == "likely_starter"]
    rotation = [r for r in rows if r["squad_role"] == "rotation"]
    assert len(starters) == ws.STARTING_PLAYER_COUNT == 11
    assert len(rotation) == ws.ROTATION_PLAYER_COUNT == 4


def test_candidate_pool_count_and_positions():
    assert len(ws.CANDIDATE_POOL) == 8
    positions = [c["primary_position"].lower() for c in ws.CANDIDATE_POOL]
    assert positions.count("goalkeeper") == 2
    assert positions.count("right-back") == 2
    assert positions.count("centre-back") == 1
    assert positions.count("midfielder") == 2
    assert positions.count("striker") == 1


def test_named_external_candidates_present():
    names = {c["name"] for c in ws.CANDIDATE_POOL}
    assert "Ron Ben Ari" in names
    assert "Omer Azulay" in names
    assert "Yossi Levi" in names


def test_ron_ben_ari_not_in_club_squad():
    club_names = {r["name"] for r in _load_squad_rows()}
    assert "Ron Ben Ari" not in club_names


def test_suggested_prompts_grounded():
    labels = [p["label"] for p in ws.SUGGESTED_PROMPTS]
    assert any("squad weaknesses" in x.lower() for x in labels)
    assert any("right-back" in x.lower() for x in labels)
    assert any("goalkeeper" in x.lower() for x in labels)
    assert any("formation" in x.lower() for x in labels)


def test_demo_season_namespace_constant():
    assert ws.DEMO_SEASON_ID == "opening-season-demo-v1"


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    import config
    import database

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


def test_api_opening_season_workspace_endpoint():
    import app as flask_app

    flask_app.app.config["TESTING"] = True
    client = flask_app.app.test_client()
    resp = client.get("/api/opening-season/workspace")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["club_player_count"] == 15
    assert data["candidate_pool_count"] == 8
    assert len(data["club_knowledge"]) >= 7
    assert len(data["candidate_pool"]) == 8


def test_session_documents_separate_pool_from_uploads():
    import app as flask_app
    import database

    flask_app.app.config["TESTING"] = True
    session = database.create_session()
    client = flask_app.app.test_client()
    resp = client.get(f"/api/sessions/{session['id']}/documents")
    data = resp.get_json()
    pool_names = {d["name"] for d in data["candidate_pool"]}
    upload_names = {d.get("display_name") for d in data["session_uploads"]}
    assert "Ron Ben Ari" in pool_names
    assert "Ron Ben Ari" not in upload_names


def test_status_includes_opening_season_counts():
    import app as flask_app
    import config as app_config

    flask_app.app.config["TESTING"] = True
    with patch.object(flask_app, "recruitment_advisor_enabled", return_value=True):
        with patch.object(flask_app.engine, "ready", True):
            with patch.object(flask_app.engine, "status", "ready"):
                with patch.object(flask_app, "_is_aws_kb_mode", return_value=True):
                    with patch.object(app_config, "validate_aws_config", return_value=[]):
                        resp = flask_app.app.test_client().get("/api/status")
    data = resp.get_json()
    assert data.get("club_player_count") == 15
    assert data.get("candidate_pool_count") == 8


def test_demo_budget_ignores_old_season(monkeypatch):
    import importlib.util

    shared = ROOT / "infra/scoutmatch_agent_extension/lambdas/shared_football"
    monkeypatch.setenv("SCOUTMATCH_USE_LOCAL_STORE", "true")
    monkeypatch.setenv("SCOUTMATCH_DEMO_SEASON_ID", "opening-season-demo-v1")

    def _load(name: str):
        spec = importlib.util.spec_from_file_location(f"sm_{name}", shared / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    operations_store = _load("operations_store")
    sys.modules["operations_store"] = operations_store
    budget_ledger = _load("budget_ledger")
    operations_store._LOCAL_STORE.clear()
    operations_store.put_item(
        entity_key="budget_ledger#old1",
        item_type="BUDGET_LEDGER",
        payload={
            "entry_type": "RESERVATION",
            "reserved_amount_eur": 129000,
            "demo_season_id": "legacy-demo",
        },
    )
    operations_store.put_item(
        entity_key="budget_ledger#new1",
        item_type="BUDGET_LEDGER",
        payload={
            "entry_type": "RESERVATION",
            "reserved_amount_eur": 43000,
            "demo_season_id": "opening-season-demo-v1",
        },
    )
    assert budget_ledger.sum_reserved_amounts() == 43000


def test_index_html_user_facing_labels():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert "Scout smarter" in html
    assert "Build the season" in html
    assert "AWS Bedrock KB connected" not in html
    assert "GROUNDED ANSWERS ONLY" not in html.upper()
    assert "Recruitment Candidate Pool" in html
    assert "System status" in html


def test_index_html_no_prominent_aws_badges():
    html = (ROOT / "templates/index.html").read_text(encoding="utf-8")
    assert "badge--aws" not in html
    assert "badge--strict" not in html
