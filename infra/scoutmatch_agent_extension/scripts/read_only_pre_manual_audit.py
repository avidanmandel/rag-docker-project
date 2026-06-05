#!/usr/bin/env python3
"""Read-only pre-manual audit — sanitized output only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
AGENT_NAME = "scoutmatch-recruitment-agent-user5-avidan"
GUARDRAIL_NAME = "scoutmatch-guardrail-user5-avidan"
KB_NAME = "knowledge-base-user5"
DATA_SOURCE_NAME = "scoutmatch-player-documents"
SNS_TOPIC = "ScoutMatchManagementNotificationsAvidan"
LINEUP_PREFIX = "scoutmatch/football-operations/lineups/"
TACTICAL_PREFIX = "scoutmatch/knowledge-base/tactical/"

FINAL_ACTION_GROUPS = {
    "ScoutMatchTacticsActionsAvidan",
    "ScoutMatchPlayerSelectionActionsAvidan",
    "ScoutMatchLineupActionsAvidan",
    "ScoutMatchLineupBoardActionsAvidan",
}
FINAL_LAMBDAS = {
    "ScoutMatchPlanMatchTacticsAvidan",
    "ScoutMatchSubmitPlayerSelectionAvidan",
    "ScoutMatchFinalizeCurrentLineupAvidan",
    "ScoutMatchGenerateLineupBoardAvidan",
}
LEGACY_GROUPS = {
    "ScoutMatchNativeActionsAvidan",
    "ScoutMatchFootballOperationsActionsAvidan",
    "ScoutMatchBudgetActionsAvidan",
    "ScoutMatchRightBackActionsAvidan",
    "ScoutMatchBelowStrikerActionsAvidan",
    "ScoutMatchForwardActionsAvidan",
    "ScoutMatchShortlistActionsAvidan",
    "ScoutMatchRecruitmentBriefActionsAvidan",
    "ScoutMatchRecruitmentWorkflowActionsAvidan",
}
LEGACY_LAMBDAS = {
    "ScoutMatchNativeToolsAvidan",
    "ScoutMatchBudgetImpactAvidan",
    "ScoutMatchRightBackFitAvidan",
    "ScoutMatchBelowStrikerFitAvidan",
    "ScoutMatchForwardFitAvidan",
}


def _find_agent_id(client) -> str | None:
    token = None
    while True:
        kwargs = {"nextToken": token} if token else {}
        page = client.list_agents(**kwargs)
        for summary in page.get("agentSummaries", []):
            if summary.get("agentName") == AGENT_NAME:
                return summary.get("agentId")
        token = page.get("nextToken")
        if not token:
            return None


def _find_kb_id(client) -> str | None:
    token = None
    while True:
        kwargs = {"nextToken": token} if token else {}
        page = client.list_knowledge_bases(**kwargs)
        for summary in page.get("knowledgeBaseSummaries", []):
            if summary.get("name") == KB_NAME:
                return summary.get("knowledgeBaseId")
        token = page.get("nextToken")
        if not token:
            return None


def _ingestion_status(client, kb_id: str) -> dict:
    out = {"latest_status": "UNKNOWN", "tactical_objects_count": 0}
    try:
        sources = client.list_data_sources(knowledgeBaseId=kb_id).get("dataSourceSummaries", [])
        ds_id = None
        for item in sources:
            if item.get("name") == DATA_SOURCE_NAME:
                ds_id = item.get("dataSourceId")
                break
        if not ds_id:
            out["latest_status"] = "DATA_SOURCE_NOT_FOUND"
            return out
        jobs = client.list_ingestion_jobs(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            maxResults=5,
        ).get("ingestionJobSummaries", [])
        if jobs:
            out["latest_status"] = jobs[0].get("status", "UNKNOWN")
            started = jobs[0].get("startedAt")
            out["latest_started_at"] = started.isoformat() if hasattr(started, "isoformat") else str(started or "")
        else:
            out["latest_status"] = "NO_JOBS"
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        out["latest_status"] = f"DENIED:{code}"
    return out


def _sns_status() -> dict:
    sns = boto3.client("sns", region_name=REGION)
    out = {"topic_exists": False, "confirmed_email_subscriptions": 0, "pending_subscriptions": 0}
    try:
        topics = sns.list_topics().get("Topics", [])
        topic_arn = None
        for item in topics:
            arn = item.get("TopicArn", "")
            if arn.endswith(f":{SNS_TOPIC}"):
                topic_arn = arn
                break
        if not topic_arn:
            return out
        out["topic_exists"] = True
        subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn).get("Subscriptions", [])
        for sub in subs:
            if (sub.get("Protocol") or "").lower() != "email":
                continue
            status = (sub.get("SubscriptionArn") or "").lower()
            if status == "pendingconfirmation":
                out["pending_subscriptions"] += 1
            elif status and "pending" not in status:
                out["confirmed_email_subscriptions"] += 1
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        out["error"] = code
    return out


def _s3_lineup_prefix(bucket: str) -> dict:
    s3 = boto3.client("s3", region_name=REGION)
    out = {"prefix_accessible": False, "object_count_sample": 0}
    try:
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=LINEUP_PREFIX, MaxKeys=10)
        out["prefix_accessible"] = True
        out["object_count_sample"] = len(resp.get("Contents", []))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        out["error"] = code
    return out


def _ddb_status() -> dict:
    ddb = boto3.client("dynamodb", region_name=REGION)
    out = {
        "dedicated_table_exists": False,
        "fallback_table_exists": False,
        "fallback_prefix_design": "football_ops#",
        "fallback_hash_key": "candidate_key",
    }
    for table, key in (
        ("ScoutMatchFootballOperationsAvidan", "dedicated_table_exists"),
        ("ScoutMatchRecruitmentShortlistAvidan", "fallback_table_exists"),
    ):
        try:
            ddb.describe_table(TableName=table)
            out[key] = True
        except ClientError:
            pass
    return out


def main() -> int:
    agent = boto3.client("bedrock-agent", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)

    report: dict = {
        "audit_time_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "agent_name": AGENT_NAME,
        "agent_found": False,
        "agent_status": "",
        "guardrail_name": GUARDRAIL_NAME,
        "guardrail_attached": False,
        "knowledge_base_name": KB_NAME,
        "knowledge_base_attached": False,
        "knowledge_base_association_enabled": False,
        "final_action_groups_enabled": [],
        "final_action_groups_count": 0,
        "legacy_action_groups_enabled": [],
        "legacy_action_groups_detached": True,
        "final_lambdas_exist": {},
        "legacy_lambdas_preserved": {},
        "kb_ingestion": {},
        "sns": {},
        "s3_lineup_prefix": {},
        "dynamodb": {},
    }

    agent_id = _find_agent_id(agent)
    if not agent_id:
        print(json.dumps(report, indent=2))
        return 1

    report["agent_found"] = True
    detail = agent.get_agent(agentId=agent_id)["agent"]
    report["agent_status"] = detail.get("agentStatus", "")
    guard = detail.get("guardrailConfiguration") or {}
    report["guardrail_attached"] = bool(guard.get("guardrailIdentifier"))

    kb_links = agent.list_agent_knowledge_bases(agentId=agent_id, agentVersion="DRAFT").get(
        "agentKnowledgeBaseSummaries", []
    )
    report["knowledge_base_attached"] = bool(kb_links)
    report["knowledge_base_association_enabled"] = any(
        (item.get("knowledgeBaseState") or "").upper() == "ENABLED" for item in kb_links
    )

    groups = agent.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT").get(
        "actionGroupSummaries", []
    )
    enabled = [
        g.get("actionGroupName")
        for g in groups
        if (g.get("actionGroupState") or "ENABLED") == "ENABLED"
    ]
    final_enabled = sorted(name for name in enabled if name in FINAL_ACTION_GROUPS)
    legacy_enabled = sorted(name for name in enabled if name in LEGACY_GROUPS)
    report["final_action_groups_enabled"] = final_enabled
    report["final_action_groups_count"] = len(final_enabled)
    report["legacy_action_groups_enabled"] = legacy_enabled
    report["legacy_action_groups_detached"] = len(legacy_enabled) == 0

    for name in FINAL_LAMBDAS:
        try:
            lam.get_function(FunctionName=name)
            report["final_lambdas_exist"][name] = True
        except ClientError:
            report["final_lambdas_exist"][name] = False

    for name in LEGACY_LAMBDAS:
        try:
            lam.get_function(FunctionName=name)
            report["legacy_lambdas_preserved"][name] = True
        except ClientError:
            report["legacy_lambdas_preserved"][name] = False

    kb_id = _find_kb_id(agent)
    if kb_id:
        report["kb_ingestion"] = _ingestion_status(agent, kb_id)
        try:
            tactical = boto3.client("s3", region_name=REGION).list_objects_v2(
                Bucket="oz-bucket-user5",
                Prefix=TACTICAL_PREFIX,
                MaxKeys=20,
            )
            report["kb_ingestion"]["tactical_objects_count"] = len(tactical.get("Contents", []))
        except ClientError as exc:
            report["kb_ingestion"]["tactical_s3_error"] = exc.response.get("Error", {}).get("Code")

    report["sns"] = _sns_status()
    report["s3_lineup_prefix"] = _s3_lineup_prefix("oz-bucket-user5")
    report["dynamodb"] = _ddb_status()

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
