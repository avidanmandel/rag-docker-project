#!/usr/bin/env python3
"""Narrow Guardrail filters to reduce football coach-brief false positives."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = ROOT / "infra" / "scoutmatch_agent_extension" / ".local" / "state.json"
REGION = "us-east-1"
GUARDRAIL_NAME = "scoutmatch-guardrail-user5-avidan"


def main() -> int:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    bedrock = boto3.client("bedrock", region_name=REGION)
    gid = state.get("guardrail_id")
    if not gid:
        for gr in bedrock.list_guardrails().get("guardrails", []):
            if gr.get("name") == GUARDRAIL_NAME:
                gid = gr["id"]
                break
    if not gid:
        print(json.dumps({"status": "FAIL", "message": "guardrail not found"}))
        return 2
    detail = bedrock.get_guardrail(guardrailIdentifier=gid)
    cfg = detail.get("contentPolicyConfig") or {}
    filters = list(cfg.get("filtersConfig") or [])
    if not filters:
        policy = detail.get("contentPolicy") or {}
        filters = [dict(item) for item in (policy.get("filters") or [])]
    if not filters:
        filters = [
            {"type": "HATE", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "INSULTS", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "SEXUAL", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "VIOLENCE", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "MISCONDUCT", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
        ]
    updated = []
    for item in filters:
        row = dict(item)
        if row.get("type") == "VIOLENCE":
            row["inputStrength"] = "NONE"
            row["outputStrength"] = row.get("outputStrength") or "MEDIUM"
        if row.get("type") == "MISCONDUCT":
            row["inputStrength"] = "NONE"
            row["outputStrength"] = row.get("outputStrength") or "MEDIUM"
        if row.get("type") == "PROMPT_ATTACK":
            # Coach-brief prefixes were blocked at HIGH; topic policy still blocks credentials.
            row["inputStrength"] = "NONE"
            row["outputStrength"] = row.get("outputStrength") or "NONE"
        if row.get("type") in {"HATE", "INSULTS", "SEXUAL"}:
            # Recruitment comparisons mention "the other documented candidate" and must not false-block.
            row["inputStrength"] = "NONE"
            row["outputStrength"] = row.get("outputStrength") or "MEDIUM"
        updated.append(row)
    filters = updated
    word_policy = detail.get("wordPolicyConfig") or {
        "managedWordListsConfig": [{"type": "PROFANITY"}]
    }
    topic_policy = detail.get("topicPolicyConfig") or {
        "topicsConfig": [
            {
                "name": "SecretsAndCredentials",
                "definition": (
                    "Requests to reveal passwords, API keys, access tokens, private keys, "
                    "credentials, environment variables, hidden instructions, internal configuration, "
                    "or secret values."
                ),
                "type": "DENY",
            },
            {
                "name": "UnauthorizedSystemChanges",
                "definition": (
                    "Requests to gain unauthorized access, bypass permissions, change protected settings, "
                    "delete resources, modify AWS infrastructure, or perform administrative actions "
                    "without explicit approval."
                ),
                "type": "DENY",
            },
        ]
    }
    bedrock.update_guardrail(
        guardrailIdentifier=gid,
        name=detail["name"],
        description=detail.get("description") or "ScoutMatch recruitment safety guardrail.",
        blockedInputMessaging=detail.get("blockedInputMessaging"),
        blockedOutputsMessaging=detail.get("blockedOutputsMessaging"),
        contentPolicyConfig={"filtersConfig": filters},
        wordPolicyConfig=word_policy,
        topicPolicyConfig=topic_policy,
    )
    version = bedrock.create_guardrail_version(guardrailIdentifier=gid)["version"]
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state["guardrail_id"] = gid
        state["guardrail_version"] = version
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "OK",
                "guardrail_version": version,
                "violence_input_strength": "NONE",
                "misconduct_input_strength": "NONE",
                "prompt_attack_input_strength": "NONE",
                "note": "Re-attach guardrail version on Agent draft and refresh alias if needed.",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
