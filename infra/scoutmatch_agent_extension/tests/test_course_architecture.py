"""Architecture expectations: v14 KB path vs Recruitment Advisor invoke_agent path."""

import inspect
from unittest.mock import MagicMock, patch

import aws_kb_engine
import bedrock_agent_service as advisor


def test_v14_engine_uses_retrieve_not_invoke_agent():
    source = inspect.getsource(aws_kb_engine.AWSKnowledgeBaseEngine)
    assert ".retrieve(" in source or "retrieve(" in source
    assert "invoke_agent" not in source


def test_recruitment_advisor_uses_invoke_agent():
    with patch.object(advisor, "AGENT_ENABLED", True), patch.object(advisor, "AGENT_ID", "A"), patch.object(
        advisor, "AGENT_ALIAS_ID", "B"
    ), patch.object(advisor.boto3, "client") as mock_client:
        mock_rt = MagicMock()
        mock_client.return_value = mock_rt
        mock_rt.invoke_agent.return_value = {"completion": []}
        advisor.invoke_agent("Who should we sign?", session_id="advisor-abc")
        mock_client.assert_called_with("bedrock-agent-runtime", region_name=advisor.AWS_REGION)
        mock_rt.invoke_agent.assert_called_once()
