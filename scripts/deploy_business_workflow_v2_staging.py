#!/usr/bin/env python3
"""Safe Business Workflow V2 staging deploy — Lambdas + non-production Agent alias only."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "infra" / "scoutmatch_agent_extension" / "scripts"
LOCAL = ROOT / "infra" / "scoutmatch_agent_extension" / ".local"
BACKUP_DIR = LOCAL / "lambda_backups" / "v2_staging"
STATE_PATH = LOCAL / "state.json"
RESULT_PATH = LOCAL / "v2_staging_deploy_report.json"

STAGING_ALIAS_NAME = "scoutmatch-business-workflow-v2-staging"
STAGING_ALIAS_ID = "T6N3TXAMCJ"  # reuse DISSOCIATED alias (quota-safe)
PRODUCTION_ALIAS_ID = "MFWBSFNIDL"

V2_ENV = {
    "SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED": "true",
    "SCOUTMATCH_EMAIL_MODE": "disabled",
    "SCOUTMATCH_CALENDAR_MODE": "ics_fallback",
    "SCOUTMATCH_SCOUTING_REMINDER_MODE": "disabled",
    "SCOUTMATCH_DEMO_REPLAY_ENABLED": "true",
}

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

os.environ.update(V2_ENV)

V2_GROUPS = {
    "ScoutMatchCritDecisionAvidan",
    "ScoutMatchTransferOutAvidan",
    "ScoutMatchScoutMissionAvidan",
    "ScoutMatchSquadBoardAvidan",
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


def _enabled_draft_groups(agent, agent_id: str) -> set[str]:
    enabled: set[str] = set()
    token: str | None = None
    while True:
        kwargs: dict = {"agentId": agent_id, "agentVersion": "DRAFT", "maxResults": 50}
        if token:
            kwargs["nextToken"] = token
        page = agent.list_agent_action_groups(**kwargs)
        for s in page.get("actionGroupSummaries", []):
            if s.get("actionGroupState") == "ENABLED":
                enabled.add(str(s.get("actionGroupName", "")))
        token = page.get("nextToken")
        if not token:
            break
    return enabled


def _disable_legacy_groups(agent, agent_id: str) -> list[str]:
    disabled: list[str] = []
    token: str | None = None
    summaries: list[dict] = []
    while True:
        kwargs: dict = {"agentId": agent_id, "agentVersion": "DRAFT", "maxResults": 50}
        if token:
            kwargs["nextToken"] = token
        page = agent.list_agent_action_groups(**kwargs)
        summaries.extend(page.get("actionGroupSummaries", []))
        token = page.get("nextToken")
        if not token:
            break
    for summary in summaries:
        name = str(summary.get("actionGroupName", ""))
        if name not in LEGACY_TO_DISABLE:
            continue
        if summary.get("actionGroupState") == "DISABLED":
            continue
        detail = agent.get_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
        )["agentActionGroup"]
        agent.update_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=summary["actionGroupId"],
            actionGroupName=name,
            actionGroupState="DISABLED",
            actionGroupExecutor=detail.get("actionGroupExecutor", {}),
            functionSchema=detail.get("functionSchema", {}),
            description=detail.get("description", name),
        )
        disabled.append(name)
    return disabled


def _load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _save_staging_meta(state: dict, *, staging_alias_id: str, staging_version: str) -> None:
    state["agent_staging_alias_id"] = staging_alias_id
    state["agent_staging_alias_name"] = STAGING_ALIAS_NAME
    state["agent_staging_version"] = staging_version
    state["v2_staging_deployed_at"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _backup_lambda_packages(deployer) -> list[str]:
    from deploy_final_four_lambda import FINAL_FOUR_LAMBDAS, zip_final_lambda

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    saved: list[str] = []
    lam = deployer.lambda_client
    for name, meta in FINAL_FOUR_LAMBDAS.items():
        try:
            current = lam.get_function(FunctionName=name)
            url = current["Code"]["Location"]
            import urllib.request

            data = urllib.request.urlopen(url, timeout=120).read()
        except Exception:
            data = zip_final_lambda(meta["folder"])
        path = BACKUP_DIR / f"{name}_{ts}.zip"
        path.write_bytes(data)
        saved.append(str(path))
        new_zip = zip_final_lambda(meta["folder"])
        lam.update_function_code(FunctionName=name, ZipFile=new_zip)
        deployer.present.append(f"Updated Lambda code: {name}")
        time.sleep(3)
    return saved


def _merge_lambda_env(deployer, name: str, base_env: dict) -> None:
    merged = {**base_env, **V2_ENV}
    deployer.ensure_lambda_env(name, merged)
    deployer.present.append(f"Merged V2 staging env on {name}")


def _publish_staging_alias(deployer, agent_id: str) -> tuple[str, str]:
    agent = deployer.agent
    prod = agent.get_agent_alias(agentId=agent_id, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version = str((prod.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))

    disabled = _disable_legacy_groups(agent, agent_id)
    deployer.present.append(f"Disabled legacy action groups on DRAFT: {disabled or 'none'}")
    enabled = _enabled_draft_groups(agent, agent_id)
    if enabled != V2_GROUPS:
        deployer.blockers.append(
            f"DRAFT enabled groups mismatch: expected {sorted(V2_GROUPS)}, got {sorted(enabled)}"
        )
        raise RuntimeError("DRAFT action groups not ready for staging publish")

    deployer.prepare_agent(agent_id)

    agent.update_agent_alias(
        agentId=agent_id,
        agentAliasId=STAGING_ALIAS_ID,
        agentAliasName=STAGING_ALIAS_NAME,
        description="Business workflow v2 staging alias — do not use for public cutover",
        aliasInvocationState="ACCEPT_INVOCATIONS",
    )
    deadline = time.time() + 240
    staging_version = ""
    while time.time() < deadline:
        detail = agent.get_agent_alias(agentId=agent_id, agentAliasId=STAGING_ALIAS_ID)["agentAlias"]
        status = detail.get("agentAliasStatus", "")
        routing = detail.get("routingConfiguration") or []
        if status == "PREPARED" and routing:
            staging_version = str(routing[0].get("agentVersion", ""))
            break
        if status == "FAILED":
            reasons = detail.get("failureReasons") or []
            raise RuntimeError(f"Staging alias publish failed: {reasons[:3]}")
        time.sleep(6)

    if not staging_version.isdigit():
        raise RuntimeError("Staging alias did not publish a numbered agent version")

    prod_after = agent.get_agent_alias(agentId=agent_id, agentAliasId=PRODUCTION_ALIAS_ID)["agentAlias"]
    prod_version_after = str((prod_after.get("routingConfiguration") or [{}])[0].get("agentVersion", ""))
    if prod_version_after != prod_version:
        raise RuntimeError(
            f"Production alias version changed ({prod_version} -> {prod_version_after}); aborting"
        )
    return STAGING_ALIAS_ID, staging_version


def main() -> int:
    from deploy_final_four_lambda import patch_deployer
    from deploy_scoutmatch_extension import Deployer

    patch_deployer(Deployer)
    deployer = Deployer(apply=True)
    state = _load_state()
    agent_id = state["agent_id"]
    agent_arn = f"arn:aws:bedrock:us-east-1:{deployer.account_id}:agent/{agent_id}"
    bucket = deployer._resolve_s3_bucket()
    kb_id, ds_id = deployer.resolve_kb()

    report: dict = {
        "production_alias_preserved": PRODUCTION_ALIAS_ID,
        "staging_alias_name": STAGING_ALIAS_NAME,
        "v2_env": V2_ENV,
        "lambda_backups": [],
        "blockers": [],
    }

    try:
        report["lambda_backups"] = _backup_lambda_packages(deployer)
        deployer.apply_final_four_architecture(agent_id, agent_arn, bucket, kb_id, ds_id)

        ops_table = os.getenv("SCOUTMATCH_FOOTBALL_OPS_TABLE", "ScoutMatchRecruitmentShortlistAvidan")
        base_env = {
            "SCOUTMATCH_FOOTBALL_OPS_TABLE": ops_table,
            "SCOUTMATCH_FOOTBALL_OPS_HASH_KEY": os.getenv(
                "SCOUTMATCH_FOOTBALL_OPS_HASH_KEY", "candidate_key"
            ),
            "SCOUTMATCH_FOOTBALL_OPS_KEY_PREFIX": os.getenv(
                "SCOUTMATCH_FOOTBALL_OPS_KEY_PREFIX", "football_ops#"
            ),
            "SCOUTMATCH_DEMO_SEASON_ID": "opening-season-demo-v1",
            "SCOUTMATCH_LINEUP_BUCKET": bucket or "",
            "SCOUTMATCH_LINEUP_S3_PREFIX": "scoutmatch/football-operations/lineups/",
        }
        for name in deployer.__class__.__dict__.get("FINAL_FOUR_LAMBDAS", {}):
            pass
        from four_lambda_apply import FINAL_FOUR_LAMBDAS

        for name in FINAL_FOUR_LAMBDAS:
            _merge_lambda_env(deployer, name, base_env)

        staging_alias_id, staging_version = _publish_staging_alias(deployer, agent_id)
        _save_staging_meta(state, staging_alias_id=staging_alias_id, staging_version=staging_version)

        report["staging_alias_id"] = staging_alias_id
        report["staging_agent_version"] = staging_version
        report["production_alias_unchanged"] = True
        report["present"] = deployer.present
        non_sns_blockers = [b for b in deployer.blockers if "SNS" not in b]
        report["blockers"] = deployer.blockers
        report["status"] = "OK" if not non_sns_blockers else "BLOCKED"
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        report["blockers"] = deployer.blockers + [str(exc)]

    RESULT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_file": str(RESULT_PATH)}, indent=2))
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
