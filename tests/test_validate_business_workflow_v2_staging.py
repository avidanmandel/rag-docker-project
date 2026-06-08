"""Tests for alias-aware V2 staging validation helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v2_staging_validation import (  # noqa: E402
    V2_LAMBDA_ALIAS,
    V2_PROBE_MAP,
    assert_v2_probe_target,
    sanitize_public_report,
    v2_probe_target,
)


def test_v2_probe_targets_use_staging_alias():
    assert v2_probe_target("SubmitCriticalDecisionAndSendEmail") == (
        f"ScoutMatchSubmitPlayerSelectionAvidan:{V2_LAMBDA_ALIAS}"
    )
    assert v2_probe_target("OpenTransferOutReviewCase") == (
        f"ScoutMatchPlanMatchTacticsAvidan:{V2_LAMBDA_ALIAS}"
    )
    assert v2_probe_target("CreateAndReviewScoutingMission") == (
        f"ScoutMatchFinalizeCurrentLineupAvidan:{V2_LAMBDA_ALIAS}"
    )
    assert v2_probe_target("GenerateVisualSquadAndLineupBoard") == (
        f"ScoutMatchGenerateLineupBoardAvidan:{V2_LAMBDA_ALIAS}"
    )


def test_assert_v2_probe_target_rejects_latest_and_unqualified():
    with pytest.raises(ValueError, match="must not target"):
        assert_v2_probe_target("ScoutMatchSubmitPlayerSelectionAvidan:LATEST")
    with pytest.raises(ValueError, match="must use published alias"):
        assert_v2_probe_target("ScoutMatchSubmitPlayerSelectionAvidan")
    with pytest.raises(ValueError, match="must use alias"):
        assert_v2_probe_target("ScoutMatchSubmitPlayerSelectionAvidan:wrong-alias")


def test_all_mapped_functions_have_probe_targets():
    for function_name in V2_PROBE_MAP:
        target = v2_probe_target(function_name)
        assert_v2_probe_target(target)


def test_sanitize_public_report_redacts_arns_and_accounts():
    raw = {
        "arn": "arn:aws:lambda:us-east-1:123456789012:function:ScoutMatchSubmitPlayerSelectionAvidan:scoutmatch-v2-staging",
        "note": "account 123456789012 should hide",
        "alias": V2_LAMBDA_ALIAS,
    }
    clean = sanitize_public_report(raw)
    assert clean["arn"] == "<redacted-arn>"
    assert "<redacted-account>" in clean["note"]
    assert clean["alias"] == V2_LAMBDA_ALIAS
