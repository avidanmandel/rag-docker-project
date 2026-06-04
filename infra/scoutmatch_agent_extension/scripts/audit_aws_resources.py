#!/usr/bin/env python3
"""Read-only AWS inventory for ScoutMatch extension resources (sanitized stdout)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import boto3

REGION = "us-east-1"
OWNED_KEYWORDS = ("avidan", "user5", "scoutmatch", "ScoutMatch")


def _owned(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ("avidan", "user5", "scoutmatch"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    session = boto3.Session(region_name=REGION)
    agent = session.client("bedrock-agent")
    lam = session.client("lambda")
    bedrock = session.client("bedrock")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region": REGION,
        "agents": [],
        "flows": [],
        "lambdas": [],
        "guardrails": [],
        "knowledge_bases": [],
    }

    for summary in agent.list_agents().get("agentSummaries", []):
        name = summary.get("agentName", "")
        if _owned(name):
            report["agents"].append(
                {
                    "name": name,
                    "id": summary.get("agentId"),
                    "status": summary.get("agentStatus"),
                    "classification": (
                        "ACTIVE_NEW"
                        if name.startswith("scoutmatch-recruitment")
                        else "LEGACY_DEMO_KEEP"
                    ),
                }
            )

    for summary in agent.list_flows().get("flowSummaries", []):
        name = summary.get("name", "")
        if _owned(name):
            report["flows"].append(
                {
                    "name": name,
                    "id": summary.get("id"),
                    "status": summary.get("status"),
                    "classification": (
                        "ACTIVE_NEW"
                        if name.startswith("scoutmatch-recruitment")
                        else "LEGACY_DEMO_KEEP"
                    ),
                }
            )

    for fn in lam.list_functions().get("Functions", []):
        name = fn["FunctionName"]
        if _owned(name):
            report["lambdas"].append(
                {
                    "name": name,
                    "classification": (
                        "ACTIVE_NEW"
                        if name.endswith("Avidan")
                        and name.startswith("ScoutMatch")
                        and name
                        in {
                            "ScoutMatchBudgetImpactAvidan",
                            "ScoutMatchRightBackFitAvidan",
                            "ScoutMatchBelowStrikerFitAvidan",
                            "ScoutMatchForwardFitAvidan",
                        }
                        else "LEGACY_DEMO_KEEP"
                    ),
                }
            )

    for gr in bedrock.list_guardrails().get("guardrails", []):
        name = gr.get("name", "")
        if _owned(name):
            report["guardrails"].append(
                {
                    "name": name,
                    "id": gr.get("id"),
                    "classification": (
                        "ACTIVE_NEW"
                        if name == "scoutmatch-guardrail-user5-avidan"
                        else "LEGACY_DEMO_KEEP"
                    ),
                }
            )

    for kb in agent.list_knowledge_bases().get("knowledgeBaseSummaries", []):
        name = kb.get("name", "")
        if _owned(name):
            entry = {
                "name": name,
                "id": kb.get("knowledgeBaseId"),
                "classification": "SHARED_READ_ONLY",
            }
            ds_list = []
            for ds in agent.list_data_sources(knowledgeBaseId=kb["knowledgeBaseId"]).get(
                "dataSourceSummaries", []
            ):
                ds_list.append(
                    {
                        "name": ds.get("name"),
                        "status": ds.get("status"),
                        "classification": (
                            "SHARED_READ_ONLY"
                            if ds.get("name") == "scoutmatch-player-documents"
                            else "REVIEW_REQUIRED"
                        ),
                    }
                )
            entry["data_sources"] = ds_list
            report["knowledge_bases"].append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"ScoutMatch AWS inventory ({REGION})")
        for key in ("agents", "flows", "lambdas", "guardrails", "knowledge_bases"):
            print(f"\n{key}:")
            for item in report[key]:
                print(f"  - {item['name']} [{item['classification']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
