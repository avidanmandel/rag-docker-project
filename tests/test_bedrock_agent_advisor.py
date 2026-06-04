"""Recruitment Advisor UI and session behavior (local, mocked)."""

from unittest.mock import MagicMock, patch

import bedrock_agent_service as advisor


def test_same_session_reused():
    with patch.object(advisor, "AGENT_ENABLED", True), patch.object(advisor, "AGENT_ID", "A"), patch.object(
        advisor, "AGENT_ALIAS_ID", "B"
    ), patch.object(advisor.boto3, "client") as mock_client:
        mock_rt = MagicMock()
        mock_client.return_value = mock_rt
        mock_rt.invoke_agent.return_value = {"completion": []}
        first = advisor.invoke_agent("hello", session_id="sess-123")
        second = advisor.invoke_agent("follow up", session_id="sess-123")
        assert first["session_id"] == "sess-123"
        assert mock_rt.invoke_agent.call_args_list[1].kwargs["sessionId"] == "sess-123"
        assert second["session_id"] == "sess-123"


def test_new_conversation_generates_new_session_when_none():
    with patch.object(advisor, "AGENT_ENABLED", True), patch.object(advisor, "AGENT_ID", "A"), patch.object(
        advisor, "AGENT_ALIAS_ID", "B"
    ), patch.object(advisor.boto3, "client") as mock_client:
        mock_rt = MagicMock()
        mock_client.return_value = mock_rt
        mock_rt.invoke_agent.return_value = {"completion": []}
        result = advisor.invoke_agent("hello", session_id=None)
        assert result["session_id"].startswith("advisor-")


def test_disabled_message_when_flag_false():
    with patch.object(advisor, "AGENT_ENABLED", False):
        payload = advisor.disabled_response()
    assert payload["enabled"] is False
    assert "disabled" in payload["message"].lower()


def test_sanitize_arn_from_answer():
    text = advisor._sanitize_text("see arn:aws:bedrock:us-east-1:123456789012:agent/ABC")
    assert "arn:aws" not in text
