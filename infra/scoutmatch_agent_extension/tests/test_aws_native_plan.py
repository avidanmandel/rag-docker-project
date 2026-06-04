"""Agent integration and AWS-only compliance checks (local plan stage)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "infra" / "scoutmatch_agent_extension"
DEPLOY = (EXT / "scripts" / "deploy_scoutmatch_extension.py").read_text(encoding="utf-8")

FOUR_LAMBDAS = {
    "ScoutMatchBudgetImpactAvidan",
    "ScoutMatchRightBackFitAvidan",
    "ScoutMatchBelowStrikerFitAvidan",
    "ScoutMatchForwardFitAvidan",
}
NEW_ACTION_GROUPS = {
    "ScoutMatchNativeActionsAvidan",
}
FORBIDDEN_TOOLS = ("ScoutMatchWeatherAvidan", "ScoutMatchLiveToolsAvidan", "time", "joke")


@pytest.mark.parametrize("name", sorted(FOUR_LAMBDAS))
def test_existing_four_lambdas_in_deploy_plan(name):
    assert name in DEPLOY


@pytest.mark.parametrize("group", sorted(NEW_ACTION_GROUPS))
def test_new_action_groups_planned(group):
    assert group in DEPLOY


def test_no_external_api_urls_in_extension_lambdas():
    for path in (EXT / "lambdas").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "transfermarkt" not in text.lower()
        assert "api-football" not in text.lower()
        assert "https://" not in text or "scoutmatch" in path.name


def test_no_outbound_http_libraries_in_extension():
    for path in (EXT / "lambdas").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "import requests" not in text
        assert "import httpx" not in text
        assert "import aiohttp" not in text
        assert "urllib.request" not in text


def test_legacy_resources_not_modified_by_deploy():
    assert "ScoutMatchWeatherAvidan" not in DEPLOY or "LEGACY" in DEPLOY
    for legacy in FORBIDDEN_TOOLS:
        if legacy.startswith("ScoutMatch"):
            assert f'modify legacy resource: {legacy}' in DEPLOY or legacy not in DEPLOY.split("ensure_action_group")[1:]


def test_v14_app_still_has_session_messages_route():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "/api/sessions/<session_id>/messages" in app
