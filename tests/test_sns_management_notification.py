"""Regression tests for SNS management notification safety."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "infra" / "scoutmatch_agent_extension" / "lambdas" / "shared_football"

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))


def _load_sns_module():
    import importlib

    sys.modules.pop("sns_notification", None)
    import sns_notification

    return importlib.reload(sns_notification)


def test_publish_never_calls_list_topics():
    with patch("boto3.client") as mock_client:
        os.environ.pop("SCOUTMATCH_USE_LOCAL_STORE", None)
        os.environ["SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:000000000000:DemoTopic"
        sns = _load_sns_module()
        mock_client.return_value.publish.return_value = {"MessageId": "msg-1"}
        result = sns.publish_management_notification(
            {
                "candidate_name": "Ron Ben Ari",
                "target_role": "right-back",
                "salary_request_eur": 43000,
                "reservation_status": "RESERVED_PENDING_APPROVAL",
                "approval_status": "PENDING_MANAGEMENT_APPROVAL",
            },
            "PASS",
        )
        assert mock_client.return_value.list_topics.call_count == 0
        assert result.get("published") is True
    os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"


def test_publish_graceful_when_topic_missing():
    os.environ.pop("SCOUTMATCH_USE_LOCAL_STORE", None)
    os.environ.pop("SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN", None)
    sns = _load_sns_module()
    result = sns.publish_management_notification(
        {"candidate_name": "Ron Ben Ari", "target_role": "right-back"},
        "PASS",
    )
    assert result.get("published") is False
    assert result.get("mode") == "topic_missing"
    os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"


def test_publish_error_does_not_raise():
    os.environ.pop("SCOUTMATCH_USE_LOCAL_STORE", None)
    os.environ["SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:000000000000:Missing"
    sns = _load_sns_module()
    with patch("boto3.client") as mock_client:
        mock_client.return_value.publish.side_effect = Exception("NotFoundException")
        result = sns.publish_management_notification(
            {"candidate_name": "Ron Ben Ari", "target_role": "right-back"},
            "PASS",
        )
    assert result.get("published") is False
    assert result.get("mode") == "publish_error"
    os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
