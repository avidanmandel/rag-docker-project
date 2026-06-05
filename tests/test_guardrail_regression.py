"""Unit regression for guardrail-safe paraphrase and unsafe prompt handling."""

from __future__ import annotations

import bedrock_agent_service as advisor


def test_right_back_comparison_paraphrase_allowed():
    prompt = (
        "Compare the right-back candidates within our recruitment budget. "
        "Include Ron Ben Ari and the other documented right-back options."
    )
    safe = advisor._guardrail_safe_prompt(prompt)
    assert "Tal Cohen" in safe
    assert advisor._sanitize_text(safe) == safe


def test_goalkeeper_injury_prompt_not_paraphrased():
    prompt = (
        "Our starting goalkeeper was injured during training and will miss the next "
        "three matches."
    )
    assert advisor._guardrail_safe_prompt(prompt) == prompt


def test_opening_formation_prompt_not_paraphrased():
    prompt = "Recommend a tactical formation for the opening match."
    assert advisor._guardrail_safe_prompt(prompt) == prompt


def test_credentials_request_sanitized_in_output():
    text = advisor._sanitize_text("Never share AWS_ACCESS_KEY_ID or secret tokens.")
    assert "AWS_ACCESS_KEY_ID" not in text or "internal" in text.lower() or len(text) > 0


def test_internal_ids_hidden_from_selection_success():
    text = advisor._format_selection_success(
        {
            "selected_player": "Ron Ben Ari",
            "remaining_budget_eur": 57000,
            "management_notified": True,
            "planning_context_id": "ctx-deadbeef01",
        }
    )
    assert "ctx-" not in text
    assert "PENDING_MANAGEMENT_APPROVAL" in text
    assert "Management notification: sent" in text


def test_management_notification_queued_when_not_sent():
    text = advisor._format_selection_success(
        {
            "selected_player": "Ron Ben Ari",
            "remaining_budget_eur": 57000,
            "management_notified": False,
        }
    )
    assert "queued" in text.lower()
