#!/usr/bin/env python3
"""Set SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN on the four final Lambdas (runtime only)."""

from __future__ import annotations

import argparse
import json

import boto3

REGION = "us-east-1"
TOPIC_NAME = "ScoutMatchManagementNotificationsAvidan"
LAMBDAS = [
    "ScoutMatchPlanMatchTacticsAvidan",
    "ScoutMatchSubmitPlayerSelectionAvidan",
    "ScoutMatchFinalizeCurrentLineupAvidan",
    "ScoutMatchGenerateLineupBoardAvidan",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topic-arn", default="", help="Optional explicit topic ARN")
    args = parser.parse_args()

    sts = boto3.client("sts", region_name=REGION)
    account = sts.get_caller_identity()["Account"]
    topic_arn = (args.topic_arn or "").strip() or f"arn:aws:sns:{REGION}:{account}:{TOPIC_NAME}"

    lam = boto3.client("lambda", region_name=REGION)
    updated: list[str] = []
    for name in LAMBDAS:
        cfg = lam.get_function_configuration(FunctionName=name)
        env = dict(cfg.get("Environment", {}).get("Variables", {}))
        env["SCOUTMATCH_MANAGEMENT_SNS_TOPIC"] = TOPIC_NAME
        env["SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN"] = topic_arn
        if not args.dry_run:
            lam.update_function_configuration(
                FunctionName=name,
                Environment={"Variables": env},
            )
        updated.append(name)

    print(
        json.dumps(
            {
                "status": "OK",
                "dry_run": args.dry_run,
                "topic_suffix": TOPIC_NAME,
                "lambdas_updated": updated,
                "publish_permission_note": "Lambda execution role must allow sns:Publish on topic",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
