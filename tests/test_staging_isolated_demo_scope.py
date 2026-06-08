"""Tests for isolated staging demo scope helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from staging_isolated_demo_scope import create_scope, write_scope_document  # noqa: E402


def test_create_scope_has_unique_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "staging_isolated_demo_scope.SCOPE_DIR",
        tmp_path,
    )
    first = create_scope(label="test-scope")
    second = create_scope(label="test-scope")
    assert first["demo_season_id"] != second["demo_season_id"]
    assert first["planning_context_id"] != second["planning_context_id"]
    assert first["demo_scope"] == first["demo_season_id"]
    path = write_scope_document(first)
    assert path.is_file()
