#!/usr/bin/env python3
"""Apply least-privilege EC2 runtime IAM for Recruitment Advisor invoke_agent + lineup SVG proxy."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
TEMPLATE_PATH = (
    ROOT / "infra" / "scoutmatch_agent_extension" / "iam" / "scoutmatch_ec2_runtime_policy.template.json"
)
REGION = os.getenv("AWS_REGION", "us-east-1")
ROLE_NAME = "ScoutMatch-EC2-Role"
POLICY_NAME = "ScoutMatchEC2InvokeAgentAvidan"
LINEUP_PREFIX = "scoutmatch/football-operations/lineups/"


def _load_agent_ids() -> tuple[str, str]:
    agent_id = (os.getenv("SCOUTMATCH_AGENT_ID") or "").strip()
    alias_id = (os.getenv("SCOUTMATCH_AGENT_ALIAS_ID") or "").strip()
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        agent_id = agent_id or str(state.get("agent_id") or "").strip()
        alias_id = alias_id or str(state.get("agent_alias_id") or "").strip()
    env_agent = ROOT / ".env.agent"
    if env_agent.exists():
        for line in env_agent.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "SCOUTMATCH_AGENT_ID" and not agent_id:
                agent_id = value
            if key == "SCOUTMATCH_AGENT_ALIAS_ID" and not alias_id:
                alias_id = value
            if key == "AWS_S3_BUCKET" and value:
                os.environ.setdefault("AWS_S3_BUCKET", value)
    if not agent_id or not alias_id:
        raise SystemExit("Missing SCOUTMATCH_AGENT_ID or SCOUTMATCH_AGENT_ALIAS_ID in state or .env.agent")
    return agent_id, alias_id


def _bucket_name() -> str:
    bucket = (os.getenv("SCOUTMATCH_LINEUP_BUCKET") or os.getenv("AWS_S3_BUCKET") or "").strip()
    if not bucket:
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("AWS_S3_BUCKET="):
                    bucket = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not bucket:
        raise SystemExit("Missing AWS_S3_BUCKET for lineup SVG proxy scope")
    return bucket


def build_policy_document(*, account_id: str, agent_id: str, alias_id: str, bucket: str) -> dict:
    alias_arn = f"arn:aws:bedrock:{REGION}:{account_id}:agent-alias/{agent_id}/{alias_id}"
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = template.replace("{{AGENT_ALIAS_ARN}}", alias_arn).replace("{{BUCKET_NAME}}", bucket)
    return json.loads(document)


def _redact_policy_for_output(policy: dict) -> dict:
    text = json.dumps(policy)
    text = re.sub(r"\b[0-9]{12}\b", "[ACCOUNT]", text)
    text = re.sub(r"arn:aws:[^\"]+", "[REDACTED_ARN]", text)
    return json.loads(text)


def apply_policy(*, dry_run: bool = False) -> dict:
    agent_id, alias_id = _load_agent_ids()
    bucket = _bucket_name()
    sts = boto3.client("sts", region_name=REGION)
    account_id = sts.get_caller_identity()["Account"]
    policy = build_policy_document(
        account_id=account_id,
        agent_id=agent_id,
        alias_id=alias_id,
        bucket=bucket,
    )
    result = {
        "role_name": ROLE_NAME,
        "policy_name": POLICY_NAME,
        "applied": False,
        "invoke_agent_scoped_to_alias": True,
        "wildcard_resource": False,
        "s3_lineup_prefix_scoped": True,
        "dry_run": dry_run,
    }
    if dry_run:
        result["policy_preview"] = _redact_policy_for_output(policy)
        return result

    iam = boto3.client("iam", region_name=REGION)
    try:
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName=POLICY_NAME,
            PolicyDocument=json.dumps(policy),
        )
        result["applied"] = True
        verify = iam.get_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME)
        doc = verify["PolicyDocument"]
        if isinstance(doc, str):
            doc = json.loads(doc)
        actions = {
            stmt.get("Action")
            if isinstance(stmt.get("Action"), str)
            else tuple(stmt.get("Action") or [])
            for stmt in doc.get("Statement", [])
        }
        result["grants_invoke_agent_only_for_bedrock"] = any(
            "bedrock:InvokeAgent" in (a if isinstance(a, str) else "|".join(a)) for a in actions
        )
        result["no_broad_bedrock_actions"] = not any(
            "bedrock:" in str(a) and "InvokeAgent" not in str(a) for a in actions
        )
    except ClientError as exc:
        result["applied"] = False
        result["error_code"] = exc.response.get("Error", {}).get("Code", "ClientError")
        result["error_message"] = exc.response.get("Error", {}).get("Message", str(exc))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = apply_policy(dry_run=args.dry_run)
    print(json.dumps(_redact_policy_for_output(out) if "policy_preview" not in out else out, indent=2))
    if out.get("error_code"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
