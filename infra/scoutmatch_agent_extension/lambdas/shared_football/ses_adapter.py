"""Optional Amazon SES review email — non-blocking."""

from __future__ import annotations

import os

from feature_flags import email_mode


def build_review_email_body(record: dict) -> str:
    return (
        "ScoutMatch AI — management review request\n\n"
        f"Decision type: {record.get('decision_type', 'recruitment')}\n"
        f"Candidate: {record.get('candidate_name', '')}\n"
        f"Target role: {record.get('target_role', '')}\n"
        f"Reserved budget: {record.get('reserved_amount_eur', 0):,} EUR\n"
        f"Remaining budget: {record.get('remaining_budget_eur', 0):,} EUR\n"
        f"Status: {record.get('status', '')}\n"
        "This is a sanitized review notification. No transfer has been approved."
    )


def send_review_email(record: dict) -> dict:
    mode = email_mode()
    if mode not in {"ses", "enabled"}:
        return {
            "sent": False,
            "mode": "disabled",
            "user_message": (
                "The recommendation was saved for management review. "
                "External email delivery is currently unavailable."
            ),
        }
    sender = (os.getenv("SCOUTMATCH_SES_SENDER") or "").strip()
    recipient = (os.getenv("SCOUTMATCH_SES_REVIEW_RECIPIENT") or "").strip()
    if not sender or not recipient:
        return {
            "sent": False,
            "mode": "not_configured",
            "user_message": (
                "The recommendation was saved for management review. "
                "External email delivery is currently unavailable."
            ),
        }
    if os.getenv("SCOUTMATCH_USE_LOCAL_STORE", "").lower() in {"1", "true", "yes"}:
        return {
            "sent": True,
            "mode": "local_mock",
            "user_message": "Review email sent.",
        }
    try:
        import boto3

        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
        client = boto3.client("ses", region_name=region)
        client.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": "ScoutMatch AI — management review request"},
                "Body": {"Text": {"Data": build_review_email_body(record)}},
            },
        )
        return {"sent": True, "mode": "ses", "user_message": "Review email sent."}
    except Exception:
        return {
            "sent": False,
            "mode": "send_failed",
            "user_message": (
                "The recommendation was saved for management review. "
                "External email delivery is currently unavailable."
            ),
        }
