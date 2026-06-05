"""Sanitized SNS management notifications."""

from __future__ import annotations

import json
import os

SNS_TOPIC_NAME = os.getenv(
    "SCOUTMATCH_MANAGEMENT_SNS_TOPIC", "ScoutMatchManagementNotificationsAvidan"
)
_TOPIC_ARN = os.getenv("SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN", "")


def _topic_arn() -> str:
    if _TOPIC_ARN.strip():
        return _TOPIC_ARN.strip()
    import boto3

    client = boto3.client("sns")
    topics = client.list_topics().get("Topics", [])
    for topic in topics:
        if topic["TopicArn"].endswith(f":{SNS_TOPIC_NAME}"):
            return topic["TopicArn"]
    return ""


def build_management_message(selection: dict, budget_decision: str) -> str:
    return (
        "ScoutMatch Management Notification\n\n"
        f"Candidate: {selection.get('candidate_name', '')}\n"
        f"Target role: {selection.get('target_role', '')}\n"
        f"Salary request: {selection.get('salary_request_eur', 0)} EUR\n"
        f"Budget status: {budget_decision}\n"
        f"Reservation status: {selection.get('reservation_status', '')}\n"
        f"Approval status: {selection.get('approval_status', '')}\n"
        "Reason: Selected by sporting director after tactical and budget review"
    )


def publish_management_notification(selection: dict, budget_decision: str) -> dict:
    message = build_management_message(selection, budget_decision)
    if os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}:
        return {"published": True, "mode": "local", "message_preview": message[:120]}
    topic = _topic_arn()
    if not topic:
        return {
            "published": False,
            "mode": "topic_missing",
            "message": "SNS topic not configured. Manual subscription required.",
        }
    import boto3

    resp = boto3.client("sns").publish(TopicArn=topic, Message=message, Subject="ScoutMatch selection")
    return {"published": True, "message_id": resp.get("MessageId", "")}
