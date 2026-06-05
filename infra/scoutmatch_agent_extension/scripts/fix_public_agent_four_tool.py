#!/usr/bin/env python3
"""Re-point public Agent alias to corrected four-tool prepared version."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from deploy_final_four_lambda import (  # noqa: E402
    ACTION_GROUPS_DETACHED_AT_FINAL_APPLY,
    AGENT_INSTRUCTION_FINAL,
    FINAL_FOUR_LAMBDAS,
    WRITE_CONFIRM_FUNCTIONS,
    final_four_schemas,
    patch_deployer,
)
from deploy_scoutmatch_extension import Deployer, REGION, _save_state  # noqa: E402
from four_lambda_apply import FINAL_USER_FACING_FUNCTIONS  # noqa: E402

patch_deployer(Deployer)


def _refresh_draft_four_tool_groups(deployer: Deployer, agent_id: str) -> None:
    """Ensure DRAFT has only four final groups with native confirmation enabled."""
    schemas = final_four_schemas()
    for name, meta in FINAL_FOUR_LAMBDAS.items():
        try:
            fn = deployer.lambda_client.get_function(FunctionName=name)
            lambda_arn = fn["Configuration"]["FunctionArn"]
        except Exception as exc:
            deployer.blockers.append(f"Lambda missing for refresh: {name}: {exc}")
            continue
        deployer.ensure_action_group(
            agent_id,
            lambda_arn,
            meta["action_group"],
            meta["function"],
            meta["description"],
            update_if_exists=True,
            require_confirmation=meta["function"] in WRITE_CONFIRM_FUNCTIONS,
        )
    for group in ACTION_GROUPS_DETACHED_AT_FINAL_APPLY:
        deployer.detach_action_group(agent_id, group)
    detail = deployer.agent.get_agent(agentId=agent_id)["agent"]
    update_kwargs = {
        "agentId": agent_id,
        "agentName": detail["agentName"],
        "agentResourceRoleArn": detail["agentResourceRoleArn"],
        "foundationModel": detail.get("foundationModel")
        or "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
        "instruction": AGENT_INSTRUCTION_FINAL,
        "idleSessionTTLInSeconds": detail.get("idleSessionTTLInSeconds", 600),
    }
    gid = str(deployer.state.get("guardrail_id") or "").strip()
    gver = str(deployer.state.get("guardrail_version") or "1").strip()
    if not gid:
        for gr in deployer.bedrock.list_guardrails().get("guardrails", []):
            if gr.get("name") == "scoutmatch-guardrail-user5-avidan":
                gid = gr["id"]
                break
    if gid:
        update_kwargs["guardrailConfiguration"] = {
            "guardrailIdentifier": gid,
            "guardrailVersion": gver,
        }
    deployer.agent.update_agent(**update_kwargs)
    deployer.present.append("Refreshed draft four-tool groups and agent instruction")


def main() -> int:
    deployer = Deployer(apply=True)
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
        load_dotenv(ROOT / ".env.agent", override=False)
    except Exception:
        pass
    deployer.audit_existing()
    agent_id = deployer.state.get("agent_id") or deployer._find_agent_id()
    if not agent_id:
        print(json.dumps({"status": "FAIL", "message": "Agent not found"}))
        return 2
    deployer.state["agent_id"] = agent_id
    alias_before = deployer.state.get("agent_alias_id") or deployer._find_agent_alias_id(agent_id)

    _refresh_draft_four_tool_groups(deployer, agent_id)
    if deployer.blockers:
        print(json.dumps({"status": "BLOCKED", "blockers": deployer.blockers}, indent=2))
        return 2

    deployer.prepare_agent(agent_id)
    alias_after = deployer._publish_agent_alias(agent_id, snapshot_draft=True)
    if not alias_after:
        print(json.dumps({"status": "FAIL", "blockers": deployer.blockers}, indent=2))
        return 2
    deployer.state["agent_alias_id"] = alias_after
    _save_state(deployer.state)
    time.sleep(35)

    result = {
        "status": "OK",
        "alias_id_stable": alias_before == alias_after,
        "public_functions": FINAL_USER_FACING_FUNCTIONS,
        "blockers": deployer.blockers,
        "present": deployer.present[-8:],
    }
    print(json.dumps(result, indent=2))
    return 0 if not deployer.blockers else 2


if __name__ == "__main__":
    sys.exit(main())
