#!/usr/bin/env python3
"""Discover SNS topic ARN and configure SubmitPlayerSelection Lambda (runtime only)."""

from __future__ import annotations

import argparse
import json

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
TOPIC_NAME = "ScoutMatchManagementNotificationsAvidan"
PUBLISH_LAMBDA = "ScoutMatchSubmitPlayerSelectionAvidan"
OTHER_LAMBDAS = [
    "ScoutMatchPlanMatchTacticsAvidan",
    "ScoutMatchFinalizeCurrentLineupAvidan",
    "ScoutMatchGenerateLineupBoardAvidan",
]


def discover_topic_arn(*, sns_client, account_id: str) -> tuple[str, dict]:
    """Return topic ARN suffix metadata without printing full ARN."""
    meta: dict = {"topic_name": TOPIC_NAME, "region": REGION, "discovered": False}
    candidate = f"arn:aws:sns:{REGION}:{account_id}:{TOPIC_NAME}"
    try:
        attrs = sns_client.get_topic_attributes(TopicArn=candidate)
        meta["discovered"] = True
        meta["discovery_method"] = "get_topic_attributes"
        meta["subscriptions_confirmed"] = attrs["Attributes"].get("SubscriptionsConfirmed", "0")
        meta["subscriptions_pending"] = attrs["Attributes"].get("SubscriptionsPending", "0")
        return candidate, meta
    except ClientError as exc:
        meta["get_topic_error"] = exc.response.get("Error", {}).get("Code", "Error")
    try:
        topics = sns_client.list_topics().get("Topics", [])
        for topic in topics:
            if topic["TopicArn"].endswith(f":{TOPIC_NAME}"):
                meta["discovered"] = True
                meta["discovery_method"] = "list_topics"
                return topic["TopicArn"], meta
    except ClientError as exc:
        meta["list_topics_error"] = exc.response.get("Error", {}).get("Code", "Error")
    meta["discovery_method"] = "sts_constructed_fallback"
    meta["discovered"] = True
    meta["note"] = (
        "Topic ARN built from STS account id; verify with Lambda publish test "
        "(local IAM may lack SNS read permissions)."
    )
    return candidate, meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topic-arn", default="", help="Optional explicit topic ARN (not stored in git)")
    args = parser.parse_args()

    sts = boto3.client("sts", region_name=REGION)
    account_id = sts.get_caller_identity()["Account"]
    sns = boto3.client("sns", region_name=REGION)

    if (args.topic_arn or "").strip():
        topic_arn = args.topic_arn.strip()
        meta = {"discovered": True, "discovery_method": "cli_argument", "topic_name": TOPIC_NAME}
    else:
        topic_arn, meta = discover_topic_arn(sns_client=sns, account_id=account_id)

    lam = boto3.client("lambda", region_name=REGION)
    cfg = lam.get_function_configuration(FunctionName=PUBLISH_LAMBDA)
    env = dict(cfg.get("Environment", {}).get("Variables", {}))
    env["SCOUTMATCH_MANAGEMENT_SNS_TOPIC"] = TOPIC_NAME
    env["SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN"] = topic_arn
    cleared: list[str] = []
    if not args.dry_run:
        lam.update_function_configuration(
            FunctionName=PUBLISH_LAMBDA,
            Environment={"Variables": env},
        )
        for name in OTHER_LAMBDAS:
            other_cfg = lam.get_function_configuration(FunctionName=name)
            other_env = dict(other_cfg.get("Environment", {}).get("Variables", {}))
            if other_env.pop("SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN", None) or other_env.pop(
                "SCOUTMATCH_MANAGEMENT_SNS_TOPIC", None
            ):
                lam.update_function_configuration(
                    FunctionName=name,
                    Environment={"Variables": other_env},
                )
                cleared.append(name)

    print(
        json.dumps(
            {
                "status": "OK",
                "dry_run": args.dry_run,
                "lambda_configured": PUBLISH_LAMBDA,
                "topic_configured": bool(topic_arn),
                "discovery": meta,
                "cleared_from_other_lambdas": cleared,
                "publish_permission_note": "Lambda execution role must allow sns:Publish on topic",
            },
            indent=2,
        )
    )
    return 0 if meta.get("discovered") else 2


if __name__ == "__main__":
    raise SystemExit(main())
