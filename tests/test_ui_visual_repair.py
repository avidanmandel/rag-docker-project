"""Focused regression tests for homepage hero balance and chat markdown repair."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "static" / "css" / "style.css"
JS = ROOT / "static" / "js" / "app.js"
HTML = ROOT / "templates" / "index.html"


def test_homepage_hero_uses_aspect_ratio_and_contain():
    css = CSS.read_text(encoding="utf-8")
    repair = css.split("Homepage visual repair")[-1]
    assert ".messages.messages--landing .dashboard-stage" in repair
    assert "aspect-ratio: 1090 / 1095" in repair
    assert "object-fit: contain" in repair
    stage_block = repair.split(".messages.messages--landing .dashboard-stage {", 1)[1].split("}", 1)[0]
    assert "aspect-ratio: 1090 / 1095" in stage_block
    assert "height: 100%" not in stage_block


def test_homepage_hero_stage_sizes_to_viewport_not_oversized_frame():
    css = CSS.read_text(encoding="utf-8")
    repair = css.split("Homepage visual repair")[-1]
    assert "width: min(100%, calc(100vh - 220px))" in repair
    assert "max-height: calc(100vh - 220px)" in repair


def test_homepage_quick_start_grid_and_five_buttons_template():
    html = HTML.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert 'id="suggestions"' in html
    assert "grid-template-columns: repeat(2" in CSS.read_text(encoding="utf-8")
    assert "renderSuggestions" in js or "suggestions" in js


def test_opening_season_workspace_exposes_five_quick_starts():
    import opening_season_workspace as workspace

    prompts = workspace.SUGGESTED_PROMPTS + workspace.SECONDARY_PROMPTS
    assert len(prompts) == 5


def test_markdown_helpers_present_in_frontend():
    js = JS.read_text(encoding="utf-8")
    assert "function normalizeMarkdownInput" in js
    assert "function renderMarkdown" in js
    assert "function sanitizeRenderedHtml" in js
    assert "View:\\s*\\/api\\/recruitment-advisor" in js


def test_sanitize_strips_unsafe_markup_patterns():
    js = JS.read_text(encoding="utf-8")
    assert 'querySelectorAll("script, style, iframe, object, embed, link")' in js
    assert "name.startsWith(\"on\")" in js
    assert 'name === "href"' in js


def test_lineup_board_image_responsive_rules():
    css = CSS.read_text(encoding="utf-8")
    block = css.split(".lineup-board-card__image")[1].split("}", 1)[0]
    assert "max-width: 100%" in block
    assert "object-fit: contain" in block


def test_frontend_markdown_node_harness():
    node = "node"
    script = ROOT / "scripts" / "frontend_markdown_test.js"
    if sys.platform == "win32":
        try:
            subprocess.run([node, str(script)], check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pytest.skip("node unavailable or markdown harness failed")
    else:
        subprocess.run([node, str(script)], check=True, capture_output=True, text=True)


def test_homepage_template_includes_hero_artwork():
    html = HTML.read_text(encoding="utf-8")
    assert "home-dashboard-art.png" in html
    assert "dashboard-stage__panel-img" in html
