#!/usr/bin/env python3
"""Create, document, and optionally clean an isolated V2 staging demo scope."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
SCOPE_DIR = ROOT / "artifacts" / "evidence" / "business_workflow_v2_staging"
REGION = "us-east-1"
V2_ALIAS = "scoutmatch-v2-staging"
TABLE_NAME = "ScoutMatchFootballOperationsAvidan"
HASH_KEY = "entity_key"

FOUR_LAMBDAS = (
    "ScoutMatchSubmitPlayerSelectionAvidan",
    "ScoutMatchPlanMatchTacticsAvidan",
    "ScoutMatchFinalizeCurrentLineupAvidan",
    "ScoutMatchGenerateLineupBoardAvidan",
)

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


def _merge_env(base: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    merged.update(overrides)
    return merged


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_scope(*, label: str = "v2-staging-browser") -> dict:
    scope_token = uuid.uuid4().hex[:12]
    demo_season_id = f"{label}-{scope_token}"
    planning_context_id = f"ctx-{scope_token}"
    return {
        "created_at": _now(),
        "label": label,
        "demo_season_id": demo_season_id,
        "planning_context_id": planning_context_id,
        "demo_scope": demo_season_id,
        "lambda_alias": V2_ALIAS,
        "table_name": TABLE_NAME,
        "cleanup_key": "demo_season_id",
    }


def _wait_for_update(lam, name: str, *, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        cfg = lam.get_function_configuration(FunctionName=name)
        if cfg.get("LastUpdateStatus") in {None, "Successful"}:
            return
        if cfg.get("LastUpdateStatus") == "Failed":
            raise RuntimeError(f"Lambda update failed for {name}")
        time.sleep(3)
    raise TimeoutError(f"Timed out waiting for Lambda update: {name}")


def apply_scope_to_v2_alias(scope: dict, *, dry_run: bool = False) -> dict:
    """Publish a new scoutmatch-v2-staging version with an isolated demo season."""
    lam = boto3.client("lambda", region_name=REGION)
    report = {"functions": {}, "demo_season_id": scope["demo_season_id"]}
    for name in FOUR_LAMBDAS:
        alias = lam.get_alias(FunctionName=name, Name=V2_ALIAS)
        version = str(alias["FunctionVersion"])
        cfg = lam.get_function_configuration(FunctionName=name, Qualifier=version)
        base_env = dict((cfg.get("Environment") or {}).get("Variables") or {})
        v2_env = _merge_env(base_env, V2_ENV_OVERRIDES)
        v2_env["SCOUTMATCH_DEMO_SEASON_ID"] = scope["demo_season_id"]
        legacy_env = _merge_env(base_env, LEGACY_ENV_OVERRIDES)
        if dry_run:
            report["functions"][name] = {"would_set_demo_season_id": scope["demo_season_id"]}
            continue
        lam.update_function_configuration(FunctionName=name, Environment={"Variables": v2_env})
        _wait_for_update(lam, name)
        new_version = lam.publish_version(
            FunctionName=name,
            Description=f"Isolated staging scope {scope['demo_season_id'][:48]}",
        )["Version"]
        lam.update_alias(FunctionName=name, Name=V2_ALIAS, FunctionVersion=str(new_version))
        lam.update_function_configuration(FunctionName=name, Environment={"Variables": legacy_env})
        _wait_for_update(lam, name)
        report["functions"][name] = {
            "alias": V2_ALIAS,
            "published_version": str(new_version),
            "demo_season_id": scope["demo_season_id"],
            "latest_restored_to_legacy": True,
        }
        time.sleep(1)
    return report


def cleanup_scope(scope: dict, *, dry_run: bool = False) -> dict:
    """Delete DynamoDB records created for one isolated demo scope only."""
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(TABLE_NAME)
    target = scope["demo_season_id"]
    deleted = 0
    scanned = 0
    token = None
    while True:
        kwargs: dict = {}
        if token:
            kwargs["ExclusiveStartKey"] = token
        page = table.scan(**kwargs)
        for item in page.get("Items", []):
            scanned += 1
            payload_raw = item.get("operations_json") or "{}"
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload = {}
            season = str(payload.get("demo_season_id") or item.get("demo_season_id") or "").strip()
            if season != target:
                continue
            key = {HASH_KEY: item[HASH_KEY]}
            if dry_run:
                deleted += 1
                continue
            table.delete_item(Key=key)
            deleted += 1
        token = page.get("LastEvaluatedKey")
        if not token:
            break
    return {"demo_season_id": target, "scanned": scanned, "deleted": deleted, "dry_run": dry_run}


def write_scope_document(scope: dict, apply_report: dict | None = None) -> Path:
    SCOPE_DIR.mkdir(parents=True, exist_ok=True)
    doc = dict(scope)
    if apply_report:
        doc["apply_report"] = apply_report
    path = SCOPE_DIR / f"isolated_scope_{scope['demo_season_id']}.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    latest = SCOPE_DIR / "latest_isolated_scope.json"
    latest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", action="store_true", help="Create a new isolated scope document")
    parser.add_argument("--apply", action="store_true", help="Apply scope to scoutmatch-v2-staging Lambda aliases")
    parser.add_argument("--cleanup", metavar="SCOPE_JSON", help="Delete DynamoDB rows for one scope file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--label", default="v2-staging-browser")
    args = parser.parse_args(argv)

    if args.cleanup:
        scope = json.loads(Path(args.cleanup).read_text(encoding="utf-8"))
        result = cleanup_scope(scope, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0

    scope = create_scope(label=args.label)
    apply_report = None
    if args.apply:
        apply_report = apply_scope_to_v2_alias(scope, dry_run=args.dry_run)
    path = write_scope_document(scope, apply_report)
    print(json.dumps({"scope_file": str(path), "scope": scope, "apply_report": apply_report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
