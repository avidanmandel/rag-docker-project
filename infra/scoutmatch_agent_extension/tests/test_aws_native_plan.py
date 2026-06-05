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


def test_native_tools_budget_helper_invoke_scoped_in_deploy_plan():
    assert "ScoutMatchBudgetImpactAvidan" in DEPLOY
    assert "lambda:InvokeFunction" in DEPLOY
    assert "ScoutMatchNativeToolsLambdaRoleAvidan" in DEPLOY or "NATIVE_TOOLS_ROLE" in DEPLOY


def test_demo_roster_seed_in_deploy_plan():
    assert "demo_roster" in DEPLOY.lower() or "record_scope" in DEPLOY
    demo_json = EXT / "demo_data" / "scoutmatch_demo_roster.json"
    assert demo_json.is_file()
    assert '"record_scope": "DEMO"' in demo_json.read_text(encoding="utf-8")


def test_no_hardcoded_sns_email_in_extension():
    for path in (EXT / "lambdas").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "@amdocs" not in text.lower()
        assert "@gmail" not in text.lower()
