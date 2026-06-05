#!/usr/bin/env python3
"""Read-only DynamoDB demo-data audit for manual cleanup planning."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[3]
REGION = "us-east-1"
TABLE = os.getenv("SCOUTMATCH_FOOTBALL_OPS_TABLE", "ScoutMatchRecruitmentShortlistAvidan")
PREFIX = os.getenv("SCOUTMATCH_FOOTBALL_OPS_KEY_PREFIX", "football_ops#")
HASH_KEY = os.getenv("SCOUTMATCH_FOOTBALL_OPS_HASH_KEY", "candidate_key")
DOC_PATH = ROOT / "docs" / "SCOUTMATCH_DEMO_DATA_CLEANUP_AUDIT.md"
SCRIPT_PATH = ROOT / "scripts" / "cleanup_demo_football_ops_records.py"


def _redact_key(key: str) -> str:
    return re.sub(r"ron\s*ben\s*ari", "ron-[redacted]", key, flags=re.I)


def _scan_demo_records() -> dict:
    ddb = boto3.client("dynamodb", region_name=REGION)
    selection_keys: list[str] = []
    ledger_keys: list[str] = []
    other_keys: list[str] = []
    reserved_total = 0
    token = None
    while True:
        kwargs = {"TableName": TABLE}
        if token:
            kwargs["ExclusiveStartKey"] = token
        page = ddb.scan(**kwargs)
        for item in page.get("Items", []):
            raw = item.get(HASH_KEY, {}).get("S") or item.get("entity_key", {}).get("S", "")
            if not raw.startswith(PREFIX):
                continue
            logical = raw[len(PREFIX) :] if raw.startswith(PREFIX) else raw
            item_type = item.get("item_type", {}).get("S", "")
            redacted = _redact_key(logical)
            if logical.startswith("player_selection#") or item_type == "PLAYER_SELECTION":
                selection_keys.append(redacted)
            elif logical.startswith("budget_ledger#") or item_type == "BUDGET_LEDGER":
                ledger_keys.append(redacted)
                try:
                    payload = json.loads(item.get("operations_json", {}).get("S", "{}"))
                    reserved_total += int(payload.get("reserved_eur") or payload.get("amount_eur") or 0)
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            else:
                other_keys.append(f"{item_type or 'UNKNOWN'}:{redacted}")
        token = page.get("LastEvaluatedKey")
        if not token:
            break
    return {
        "table_name": TABLE,
        "player_selection_count": len(selection_keys),
        "budget_ledger_count": len(ledger_keys),
        "other_demo_count": len(other_keys),
        "reserved_budget_total_eur": reserved_total,
        "selection_keys_sample": selection_keys[:8],
        "ledger_keys_sample": ledger_keys[:8],
        "other_keys_sample": other_keys[:8],
    }


def _write_cleanup_script() -> None:
    SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRIPT_PATH.write_text(
        """#!/usr/bin/env python3
\"\"\"Manual demo cleanup — requires explicit operator confirmation.\"\"\"

from __future__ import annotations

import sys

CONFIRM_PHRASE = "DELETE_DEMO_FOOTBALL_OPS_ONLY"


def main() -> int:
    print("This script is intentionally disabled by default.")
    print("It deletes only football_ops# demo PLAYER_SELECTION and BUDGET_LEDGER records.")
    print(f"To proceed, rerun with: python {__file__} {CONFIRM_PHRASE}")
    if len(sys.argv) < 2 or sys.argv[1] != CONFIRM_PHRASE:
        return 2
    print("Cleanup execution is not automated in this repository build.")
    print("Perform deletion manually in DynamoDB console using the audit criteria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )


def _write_doc(report: dict, *, access_denied: bool) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# ScoutMatch Demo Data Cleanup Audit",
        "",
        f"Generated: {stamp}",
        "",
        "## Read-only audit result",
        "",
        f"- DynamoDB table: `{report.get('table_name', TABLE)}`",
        f"- PLAYER_SELECTION demo records: **{report.get('player_selection_count', 'unknown')}**",
        f"- BUDGET_LEDGER demo records: **{report.get('budget_ledger_count', 'unknown')}**",
        f"- Other football_ops demo records: **{report.get('other_demo_count', 'unknown')}**",
        f"- Total demo reserved budget (ledger scan): **{report.get('reserved_budget_total_eur', 'unknown')} EUR**",
        "",
        "## Sanitized record identifiers (sample)",
        "",
        "### PLAYER_SELECTION",
        "",
    ]
    for key in report.get("selection_keys_sample") or []:
        lines.append(f"- `{key}`")
    lines.extend(["", "### BUDGET_LEDGER", ""])
    for key in report.get("ledger_keys_sample") or []:
        lines.append(f"- `{key}`")
    lines.extend(
        [
            "",
            "## Safe deletion criteria",
            "",
            "- Delete only items whose hash key begins with `football_ops#player_selection#` from demo browser tests.",
            "- Delete only items whose hash key begins with `football_ops#budget_ledger#` created by demo selection tests.",
            "- Do not delete baseline club knowledge, production shortlist records, or non-demo lineup records.",
            "- Do not delete SNS topics, Lambdas, Agent versions, or Knowledge Base assets.",
            "",
            "## Execution status",
            "",
            "- Automatic deletion executed: **no**",
            "- Production records touched: **no**",
            "",
            "## Prepared manual cleanup",
            "",
            f"- Script: `{SCRIPT_PATH.as_posix()}`",
            "- Requires explicit confirmation phrase before any operator action.",
            "",
        ]
    )
    if access_denied:
        lines.extend(
            [
                "## Audit limitation",
                "",
                "- Local principal lacked DynamoDB scan permission; counts may be incomplete.",
                "- Re-run this audit from an authorized EC2 or IAM principal before cleanup.",
                "",
            ]
        )
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    access_denied = False
    try:
        report = _scan_demo_records()
    except ClientError as exc:
        access_denied = exc.response.get("Error", {}).get("Code") == "AccessDeniedException"
        report = {
            "table_name": TABLE,
            "player_selection_count": "audit_incomplete",
            "budget_ledger_count": "audit_incomplete",
            "other_demo_count": "audit_incomplete",
            "reserved_budget_total_eur": "audit_incomplete",
            "selection_keys_sample": [],
            "ledger_keys_sample": [],
            "other_keys_sample": [],
            "error_code": exc.response.get("Error", {}).get("Code"),
        }
    _write_cleanup_script()
    _write_doc(report, access_denied=access_denied)
    print(json.dumps({"doc": str(DOC_PATH), "cleanup_script": str(SCRIPT_PATH), **report}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
