"""Mocked tests for optional Bedrock Flow Flask endpoint."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("RAG_BACKEND", "aws_kb")
os.environ.setdefault("BEDROCK_KB_ID", "TEST_KB")
os.environ.setdefault("BEDROCK_DATA_SOURCE_ID", "TEST_DS")
os.environ.setdefault("BEDROCK_MODEL_ARN", "arn:aws:bedrock:us-east-1::foundation-model/test")
os.environ.setdefault("AWS_S3_BUCKET", "test-scoutmatch-bucket")
os.environ.setdefault("AWS_S3_PREFIX", "scoutmatch/knowledge-base/")
os.environ["SCOUTMATCH_FLOW_EXTENSION_ENABLED"] = "false"

import app as flask_app  # noqa: E402
import bedrock_flow_service  # noqa: E402


class RecruitmentFlowExtensionTests(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.app.test_client()

    def test_flow_endpoint_disabled_by_default(self):
        resp = self.client.post(
            "/api/recruitment-flow/chat",
            json={"content": "What is the transfer budget?"},
        )
        self.assertEqual(resp.status_code, 503)
        data = resp.get_json()
        self.assertFalse(data.get("enabled"))
        self.assertIn("disabled", data.get("message", "").lower())

    @patch("bedrock_flow_service.boto3")
    def test_flow_endpoint_enabled_mocked(self, mock_boto3):
        mock_client = mock_boto3.client.return_value
        mock_client.invoke_flow.return_value = {
            "responseStream": [
                {
                    "flowOutputEvent": {
                        "content": {"document": "Maximum combined budget is 100,000 EUR."}
                    }
                }
            ]
        }
        with (
            patch.object(bedrock_flow_service, "FLOW_ENABLED", True),
            patch.object(bedrock_flow_service, "FLOW_ID", "FLOW123"),
            patch.object(bedrock_flow_service, "FLOW_ALIAS_ID", "ALIAS123"),
        ):
            result = bedrock_flow_service.invoke_flow("budget?")
        self.assertTrue(result.get("enabled"))
        self.assertIn("100,000", result.get("answer", ""))


if __name__ == "__main__":
    unittest.main()
