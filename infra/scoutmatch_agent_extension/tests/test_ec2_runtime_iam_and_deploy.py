"""EC2 runtime IAM policy and deployment script port-mapping tests."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_recruitment_advisor_ec2.sh"
TEMPLATE = (
    ROOT
    / "infra"
    / "scoutmatch_agent_extension"
    / "iam"
    / "scoutmatch_ec2_runtime_policy.template.json"
)
APPLY_SCRIPT = ROOT / "scripts" / "apply_ec2_invoke_agent_iam.py"


def _load_apply_module():
    spec = importlib.util.spec_from_file_location("apply_ec2_invoke_agent_iam", APPLY_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_deploy_script_public_cutover_uses_port_80():
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "-p 0.0.0.0:80:5000" in text
    assert "-p 0.0.0.0:5000:5000" not in text


def test_deploy_script_rollback_uses_port_80():
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "ROLLBACK:" in text
    assert re.search(r"ROLLBACK:.*-p 0\.0\.0\.0:80:5000", text)


def test_deploy_script_staging_stays_local_5002():
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "-p 127.0.0.1:5002:5000" in text
    assert text.count("-p 127.0.0.1:5002:5000") >= 1


def test_iam_template_grants_only_invoke_agent_for_bedrock():
    doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    bedrock_actions: list[str] = []
    for stmt in doc["Statement"]:
        action = stmt.get("Action", [])
        if isinstance(action, str):
            action = [action]
        for item in action:
            if str(item).startswith("bedrock:"):
                bedrock_actions.append(str(item))
    assert bedrock_actions == ["bedrock:InvokeAgent"]


def test_iam_template_uses_exact_alias_placeholder_not_wildcard():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "{{AGENT_ALIAS_ARN}}" in text
    assert '"*"' not in text
    assert "Resource" in text


def test_iam_template_s3_scoped_to_lineup_prefix_only():
    doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    get_stmt = next(
        s for s in doc["Statement"] if s.get("Action") == ["s3:GetObject"]
    )
    list_stmt = next(
        s for s in doc["Statement"] if s.get("Action") == ["s3:ListBucket"]
    )
    assert any("scoutmatch/football-operations/lineups/*" in r for r in get_stmt["Resource"])
    prefix_cond = list_stmt.get("Condition", {}).get("StringLike", {}).get("s3:prefix", [])
    assert "scoutmatch/football-operations/lineups/*" in prefix_cond


def test_build_policy_document_scopes_alias_arn_only():
    mod = _load_apply_module()
    doc = mod.build_policy_document(
        account_id="000000000000",
        agent_id="AGENTID123",
        alias_id="ALIASID123",
        bucket="example-bucket",
    )
    bedrock_stmt = doc["Statement"][0]
    assert bedrock_stmt["Action"] == ["bedrock:InvokeAgent"]
    assert len(bedrock_stmt["Resource"]) == 1
    assert "agent-alias/AGENTID123/ALIASID123" in bedrock_stmt["Resource"][0]
    assert "*" not in bedrock_stmt["Resource"][0]


def test_lineup_proxy_requires_s3_get_and_list():
    """Flask proxy uses DynamoDB metadata + get_object with list_objects fallback."""
    service = (ROOT / "lineup_board_service.py").read_text(encoding="utf-8")
    assert "_object_key_from_metadata" in service
    assert "list_objects_v2" in service
    assert "get_object" in service
    doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    list_stmt = doc["Statement"][1]
    get_stmt = doc["Statement"][2]
    assert list_stmt["Action"] == ["s3:ListBucket"]
    assert "Condition" in list_stmt
    assert get_stmt["Action"] == ["s3:GetObject"]
    assert "Condition" not in get_stmt
    ddb_stmt = doc["Statement"][3]
    assert "dynamodb:GetItem" in ddb_stmt["Action"]
