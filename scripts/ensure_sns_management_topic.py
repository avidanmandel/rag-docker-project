#!/usr/bin/env python3
"""Ensure ScoutMatch management SNS topic exists (runtime only, no ARN in git)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"))

from deploy_scoutmatch_extension import Deployer  # noqa: E402

TOPIC_SUFFIX = "ScoutMatchManagementNotificationsAvidan"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    deployer = Deployer(apply=args.apply)
    arn = deployer.ensure_sns_topic()
    topic_ready = bool(arn) and not deployer.blockers
    payload = {
        "status": "OK" if topic_ready else "MANUAL_REQUIRED",
        "topic_suffix": TOPIC_SUFFIX,
        "topic_ready": topic_ready,
        "apply": args.apply,
        "blockers": deployer.blockers,
        "manual_console_steps": [
            "AWS Console → Amazon SNS → Topics → Create topic",
            f"Name: {TOPIC_SUFFIX}",
            "Then run: python scripts/configure_sns_lambda_env.py",
            "Optional email subscription: see docs/SCOUTMATCH_SNS_EMAIL_SUBSCRIPTION_GUIDE.md",
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0 if topic_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
