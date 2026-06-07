#!/usr/bin/env python3
"""Restore production-safe Lambda $LATEST and isolate V2 staging via Lambda aliases."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"
LOCAL = ROOT / "infra" / "scoutmatch_agent_extension" / ".local"
RESULT_PATH = LOCAL / "lambda_production_isolation_report.json"
STATE_PATH = LOCAL / "state.json"

REGION = "us-east-1"
AGENT_ID = "3YMQVGTYSG"
PRODUCTION_ALIAS_ID = "MFWBSFNIDL"
STAGING_ALIAS_ID = "T6N3TXAMCJ"
STAGING_ALIAS_NAME = "scoutmatch-business-workflow-v2-staging"

PRODUCTION_LAMBDA_ALIAS = "scoutmatch-production-stable"
V2_LAMBDA_ALIAS = "scoutmatch-v2-staging"

LEGACY_ENV_OVERRIDES = {
    "SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED": "false",
    "SCOUTMATCH_EMAIL_MODE": "disabled",
    "SCOUTMATCH_CALENDAR_MODE": "ics_fallback",
    "SCOUTMATCH_SCOUTING_REMINDER_MODE": "disabled",
    "SCOUTMATCH_DEMO_REPLAY_ENABLED": "false",
}

V2_ENV_OVERRIDES = {
    "SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED": "true",
    "SCOUTMATCH_EMAIL_MODE": "disabled",
    "SCOUTMATCH_CALENDAR_MODE": "ics_fallback",
    "SCOUTMATCH_SCOUTING_REMINDER_MODE": "disabled",
    "SCOUTMATCH_DEMO_REPLAY_ENABLED": "true",
}

V2_ACTION_GROUPS = {
    "ScoutMatchCritDecisionAvidan": "ScoutMatchSubmitPlayerSelectionAvidan",
    "ScoutMatchTransferOutAvidan": "ScoutMatchPlanMatchTacticsAvidan",
    "ScoutMatchScoutMissionAvidan": "ScoutMatchFinalizeCurrentLineupAvidan",
    "ScoutMatchSquadBoardAvidan": "ScoutMatchGenerateLineupBoardAvidan",
}

LEGACY_TO_DISABLE = {
    "ScoutMatchTacticsActionsAvidan",
    "ScoutMatchSelectionAgAvidan",
    "ScoutMatchLineupActionsAvidan",
    "ScoutMatchLineupBoardActionsAvidan",
    "ScoutMatchPlayerSelectionActionsAvidan",
    "ScoutMatchCriticalDecisionActionsAvidan",
    "ScoutMatchTransferOutActionsAvidan",
    "ScoutMatchScoutingMissionActionsAvidan",
    "ScoutMatchSquadBoardActionsAvidan",
}

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _merge_env(base: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    merged.update(overrides)
    return merged


def _wait_for_update(lam, name: str, *, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        cfg = lam.get_function_configuration(FunctionName=name)
        if cfg.get("LastUpdateStatus") in {None, "Successful"}:
            return
        if cfg.get("LastUpdateStatus") == "Failed":
            reasons = cfg.get("LastUpdateStatusReason", "")
            raise RuntimeError(f"Lambda update failed for {name}: {reasons}")
        time.sleep(3)
    raise TimeoutError(f"Timed out waiting for Lambda update: {name}")


def _publish_version(lam, name: str, description: str) -> str:
    resp = lam.publish_version(FunctionName=name, Description=description[:256])
    return str(resp["Version"])


def _ensure_alias(lam, account_id: str, name: str, alias: str, version: str) -> str:
    try:
        lam.create_alias(
            FunctionName=name,
            Name=alias,
            FunctionVersion=version,
            Description=f"ScoutMatch isolation alias ({alias})",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise
        lam.update_alias(FunctionName=name, Name=alias, FunctionVersion=version)
    detail = lam.get_alias(FunctionName=name, Name=alias)
    return detail["AliasArn"]


def _deploy_fixed_code(lam) -> list[str]:
    from deploy_final_four_lambda import FINAL_FOUR_LAMBDAS, zip_final_lambda

    updated: list[str] = []
    for name, meta in FINAL_FOUR_LAMBDAS.items():
        lam.update_function_code(FunctionName=name, ZipFile=zip_final_lambda(meta["folder"]))
        _wait_for_update(lam, name)
        updated.append(name)
        time.sleep(2)
    return updated


def _isolate_lambda(lam, account_id: str, name: str, base_env: dict[str, str]) -> dict:
    legacy_env = _merge_env(base_env, LEGACY_ENV_OVERRIDES)
    v2_env = _merge_env(base_env, V2_ENV_OVERRIDES)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lam.update_function_configuration(FunctionName=name, Environment={"Variables": legacy_env})
    _wait_for_update(lam, name)
    legacy_version = _publish_version(lam, name, f"legacy-stable-{ts}")

    lam.update_function_configuration(FunctionName=name, Environment={"Variables": v2_env})
    _wait_for_update(lam, name)
    v2_version = _publish_version(lam, name, f"v2-staging-{ts}")

    lam.update_function_configuration(FunctionName=name, Environment={"Variables": legacy_env})
    _wait_for_update(lam, name)

    production_alias_arn = _ensure_alias(lam, account_id, name, PRODUCTION_LAMBDA_ALIAS, legacy_version)
    staging_alias_arn = _ensure_alias(lam, account_id, name, V2_LAMBDA_ALIAS, v2_version)

    return {
        "function_name": name,
        "latest_env": "legacy",
        "legacy_version": legacy_version,
        "v2_version": v2_version,
        "production_alias": production_alias_arn,
        "staging_alias": staging_alias_arn,
        "production_agent_target": (
            f"arn:aws:lambda:{REGION}:{account_id}:function:{name} ($LATEST legacy env)"
        ),
        "staging_agent_target": staging_alias_arn,
    }


def _disable_legacy_groups(agent) -> list[str]:
    disabled: list[str] = []
    token: str | None = None
    summaries: list[dict] = []
    while True:
        kwargs: dict = {"agentId": AGENT_ID, "agentVersion": "DRAFT", "maxResults": 50}
        if token:
            kwargs["nextToken"] = token
        page = agent.list_agent_action_groups(**kwargs)
        summaries.extend(page.get("actionGroupSummaries", []))
        token = page.get("nextToken")
        if not token:
            break
    for summary in summaries:
        group_name = str(summary.get("actionGroupName", ""))
        if group_name not in LEGACY_TO_DISABLE:
            continue
        if summary.get("actionGroupState") == "DISABLED":
            continue
        detail = agent.get_agent_action_group(
            agentId=AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
        )["agentActionGroup"]
        agent.update_agent_action_group(
            agentId=AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
            actionGroupName=group_name,
            actionGroupState="DISABLED",
            actionGroupExecutor=detail.get("actionGroupExecutor", {}),
            functionSchema=detail.get("functionSchema", {}),
            description=detail.get("description", group_name),
        )
        disabled.append(group_name)
    return disabled


def _point_v2_groups_to_aliases(agent, mappings: dict[str, dict]) -> list[str]:
    updated: list[str] = []
    token: str | None = None
    summaries: list[dict] = []
    while True:
        kwargs: dict = {"agentId": AGENT_ID, "agentVersion": "DRAFT", "maxResults": 50}
        if token:
            kwargs["nextToken"] = token
        page = agent.list_agent_action_groups(**kwargs)
        summaries.extend(page.get("actionGroupSummaries", []))
        token = page.get("nextToken")
        if not token:
            break
    for summary in summaries:
        group_name = str(summary.get("actionGroupName", ""))
        lambda_name = V2_ACTION_GROUPS.get(group_name)
        if not lambda_name:
            continue
        alias_arn = mappings[lambda_name]["staging_alias"]
        detail = agent.get_agent_action_group(
            agentId=AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
        )["agentActionGroup"]
        current = detail.get("actionGroupExecutor", {}).get("lambda", "")
        if current == alias_arn:
            continue
        agent.update_agent_action_group(
            agentId=AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
            actionGroupName=group_name,
            actionGroupState="ENABLED",
            actionGroupExecutor={"lambda": alias_arn},
            functionSchema=detail.get("functionSchema", {}),
            description=detail.get("description", group_name),
        )
        updated.append(group_name)
    return updated


def _republish_staging_alias(agent) -> tuple[str, str]:
    prod_before = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version = str((prod_before.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))

    agent.prepare_agent(agentId=AGENT_ID)
    deadline = time.time() + 240
    while time.time() < deadline:
        status = agent.get_agent(agentId=AGENT_ID)["agent"].get("agentStatus", "")
        if status == "PREPARED":
            break
        if status == "FAILED":
            raise RuntimeError("Agent prepare failed during staging republish")
        time.sleep(6)

    agent.update_agent_alias(
        agentId=AGENT_ID,
        agentAliasId=STAGING_ALIAS_ID,
        agentAliasName=STAGING_ALIAS_NAME,
        description="Business workflow v2 staging alias — do not use for public cutover",
        aliasInvocationState="ACCEPT_INVOCATIONS",
    )
    staging_version = ""
    deadline = time.time() + 240
    while time.time() < deadline:
        detail = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=STAGING_ALIAS_ID)["agentAlias"]
        if detail.get("agentAliasStatus") == "PREPARED" and detail.get("routingConfiguration"):
            staging_version = str(detail["routingConfiguration"][0].get("agentVersion", ""))
            break
        if detail.get("agentAliasStatus") == "FAILED":
            reasons = detail.get("failureReasons") or []
            raise RuntimeError(f"Staging alias publish failed: {reasons[:3]}")
        time.sleep(6)

    prod_after = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version_after = str((prod_after.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))
    if prod_version_after != prod_version:
        raise RuntimeError(
            f"Production alias version changed ({prod_version} -> {prod_version_after}); aborting"
        )
    return prod_version, staging_version


def main() -> int:
    os.environ.setdefault("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", "true")
    from four_lambda_apply import FINAL_FOUR_LAMBDAS

    lam = boto3.client("lambda", region_name=REGION)
    agent = boto3.client("bedrock-agent", region_name=REGION)
    sts = boto3.client("sts", region_name=REGION)
    account_id = sts.get_caller_identity()["Account"]

    report: dict = {
        "status": "STARTED",
        "lambda_mappings": [],
        "production_agent_version_before": "",
        "staging_agent_version_after": "",
        "production_alias_unchanged": False,
        "blockers": [],
    }

    try:
        prod_before = agent.get_agent_alias(agentId=AGENT_ID, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
        report["production_agent_version_before"] = str(
            (prod_before.get("routingConfiguration") or [{}])[0].get("agentVersion", "")
        )

        report["code_updated"] = _deploy_fixed_code(lam)

        mappings: dict[str, dict] = {}
        for name in FINAL_FOUR_LAMBDAS:
            cfg = lam.get_function_configuration(FunctionName=name)
            base_env = dict((cfg.get("Environment") or {}).get("Variables") or {})
            base_env.pop("SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED", None)
            mapping = _isolate_lambda(lam, account_id, name, base_env)
            mappings[name] = mapping
            report["lambda_mappings"].append(mapping)

        report["legacy_groups_disabled"] = _disable_legacy_groups(agent)
        report["v2_groups_repointed"] = _point_v2_groups_to_aliases(agent, mappings)
        prod_version, staging_version = _republish_staging_alias(agent)
        report["production_agent_version_after"] = prod_version
        report["staging_agent_version_after"] = staging_version
        report["production_alias_unchanged"] = (
            prod_version == report["production_agent_version_before"]
        )

        if STATE_PATH.is_file():
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state["agent_staging_version"] = staging_version
            state["lambda_isolation_applied_at"] = datetime.now(timezone.utc).isoformat()
            state["lambda_production_alias"] = PRODUCTION_LAMBDA_ALIAS
            state["lambda_v2_staging_alias"] = V2_LAMBDA_ALIAS
            STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        report["status"] = "OK"
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        report["blockers"].append(str(exc))

    LOCAL.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_file": str(RESULT_PATH)}, indent=2))
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
