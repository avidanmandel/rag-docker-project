"""Root-level business workflow v2 UI and config tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def v2_enabled(monkeypatch):
    monkeypatch.setenv("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", "true")
    import config as cfg

    monkeypatch.setattr(cfg, "SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", True, raising=False)


def test_homepage_v2_headline(v2_enabled):
    import app as flask_app

    client = flask_app.app.test_client()
    resp = client.get("/api/opening-season/workspace")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["hero"]["headline"] == "Build the strongest squad for the season."
    assert len(data["suggested_prompts"]) == 5
    assert data["business_cards"][0]["value"] == "4th place"
    assert data["business_cards"][-1]["value"] == "Barcelona"


def test_feature_flag_fallback_disabled(monkeypatch):
    monkeypatch.setenv("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", "false")
    import config as cfg

    monkeypatch.setattr(cfg, "SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", False, raising=False)
    import app as flask_app

    client = flask_app.app.test_client()
    resp = client.get("/api/opening-season/workspace")
    data = resp.get_json()
    assert data.get("business_workflow_v2") is False
    assert len(data["suggested_prompts"]) == 4


def test_completed_observation_route():
    import app as flask_app

    resp = flask_app.app.test_client().get("/api/opening-season/completed-observations/ron-ben-ari")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidate_name"] == "Ron Ben Ari"
    assert data["report_type"] == "synthetic_demo_replay"


def test_calendar_invite_route():
    import app as flask_app

    resp = flask_app.app.test_client().get("/api/opening-season/calendar-invite/mission-demo123")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers.get("Content-Type", "")
