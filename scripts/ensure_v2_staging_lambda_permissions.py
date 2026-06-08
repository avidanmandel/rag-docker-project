#!/usr/bin/env python3
"""Ensure Bedrock Agent can invoke V2 staging Lambda aliases after Confirm."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
STAGING_ALIAS = "scoutmatch-v2-staging"
AGENT_ROLE = "ScoutMatchExtensionAgentRoleAvidan"
AGENT_POLICY = "ScoutMatchExtensionAgentInline"

LAMBDA_GROUPS = [
    ("ScoutMatchPlanMatchTacticsAvidan", "ScoutMatchTransferOutAvidan"),
    ("ScoutMatchSubmitPlayerSelectionAvidan", "ScoutMatchCritDecisionAvidan"),
    ("ScoutMatchFinalizeCurrentLineupAvidan", "ScoutMatchScoutMissionAvidan"),
    ("ScoutMatchGenerateLineupBoardAvidan", "ScoutMatchSquadBoardAvidan"),
]


def _load_agent_id() -> str:
    if STATE_PATH.is_file():
        agent_id = json.loads(STATE_PATH.read_text(encoding="utf-8")).get("agent_id", "")
        if agent_id:
            return str(agent_id)
    return "3YMQVGTYSG"


def _ensure_agent_role_policy(iam, account_id: str) -> None:
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    "arn:aws:bedrock:*:*:inference-profile/*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [
                    f"arn:aws:lambda:{REGION}:{account_id}:function:ScoutMatch*Avidan",
                    f"arn:aws:lambda:{REGION}:{account_id}:function:ScoutMatch*Avidan:*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
                "Resource": [f"arn:aws:bedrock:{REGION}:{account_id}:knowledge-base/*"],
            },
        ],
    }
    iam.put_role_policy(
        RoleName=AGENT_ROLE,
        PolicyName=AGENT_POLICY,
        PolicyDocument=json.dumps(policy),
    )


def _ensure_alias_permissions(lam, *, agent_arn: str, account_id: str) -> list[str]:
    added: list[str] = []
    for function_name, action_group in LAMBDA_GROUPS:
        statement_id = f"bedrock-v2-staging-{action_group}"[:80]
        try:
            lam.add_permission(
                FunctionName=function_name,
                Qualifier=STAGING_ALIAS,
                StatementId=statement_id,
                Action="lambda:InvokeFunction",
                Principal="bedrock.amazonaws.com",
                SourceArn=agent_arn,
                SourceAccount=account_id,
            )
            added.append(f"{function_name}:{STAGING_ALIAS}")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceConflictException":
                raise
    return added


def main() -> int:
    sts = boto3.client("sts", region_name=REGION)
    account_id = sts.get_caller_identity()["Account"]
    agent_id = _load_agent_id()
    agent_arn = f"arn:aws:bedrock:{REGION}:{account_id}:agent/{agent_id}"

    iam = boto3.client("iam", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)

    _ensure_agent_role_policy(iam, account_id)
    added = _ensure_alias_permissions(lam, agent_arn=agent_arn, account_id=account_id)

    print(
        json.dumps(
            {
                "status": "OK",
                "agent_role": AGENT_ROLE,
                "agent_arn": agent_arn,
                "alias_permissions_added": added,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
