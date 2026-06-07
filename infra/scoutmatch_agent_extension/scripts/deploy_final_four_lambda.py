"""Final four-Lambda / four-Action-Group deploy integration."""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from four_lambda_apply import (
    ACTION_GROUPS_DETACHED_AT_FINAL_APPLY,
    AGENT_INSTRUCTION_FINAL,
    FINAL_FOUR_LAMBDAS,
    FOOTBALL_OPS_HASH_KEY_FALLBACK,
    FOOTBALL_OPS_KEY_PREFIX_FALLBACK,
    FOOTBALL_OPS_TABLE,
    FOOTBALL_OPS_TABLE_FALLBACK,
    KB_TACTICAL_PREFIX,
    LINEUP_S3_PREFIX,
    SNS_TOPIC_NAME,
    WRITE_CONFIRM_FUNCTIONS,
    is_business_workflow_v2_enabled,
)
from demo_roster_seed import apply_demo_roster_seed, plan_demo_roster_seed

if TYPE_CHECKING:
    pass

EXT = Path(__file__).resolve().parents[1]
REGION = "us-east-1"
TAGS = {
    "Project": "ScoutMatchAI",
    "Owner": "Avidan",
    "CourseUser": "user5",
    "Environment": "demo",
    "Purpose": "scoutmatch-agent-flow-extension",
    "ManagedBy": "Cursor",
    "DoNotDeleteWithoutApproval": "true",
}
KB_DOCS = EXT / "kb_documents"


def _function_schema(
    name: str,
    description: str,
    properties: dict,
    required: list[str],
    *,
    require_confirmation: bool | None = None,
) -> dict:
    params: dict[str, dict] = {}
    for key, meta in properties.items():
        params[key] = {
            "type": meta["type"],
            "description": meta.get("description", key.replace("_", " ")),
            "required": key in required,
        }
    fn = {"name": name, "description": description, "parameters": params}
    if require_confirmation is not None:
        fn["requireConfirmation"] = "ENABLED" if require_confirmation else "DISABLED"
    return fn


def final_four_schemas() -> dict[str, dict]:
    if is_business_workflow_v2_enabled():
        return {
            "SubmitCriticalDecisionAndSendEmail": _function_schema(
                "SubmitCriticalDecisionAndSendEmail",
                "Submit a confirmed recruitment decision for management review and optional SES email.",
                {
                    "candidate_name": {"type": "string"},
                    "target_role": {"type": "string"},
                    "salary_eur": {"type": "integer"},
                    "decision_type": {"type": "string"},
                    "selection_reason": {"type": "string"},
                },
                ["candidate_name"],
                require_confirmation=True,
            ),
            "OpenTransferOutReviewCase": _function_schema(
                "OpenTransferOutReviewCase",
                "Open a transfer-out review case for a current squad player.",
                {
                    "player_name": {"type": "string"},
                    "review_reason": {"type": "string"},
                    "advisory_only": {"type": "boolean"},
                },
                [],
                require_confirmation=True,
            ),
            "CreateAndReviewScoutingMission": _function_schema(
                "CreateAndReviewScoutingMission",
                "Create a scouting mission or review a completed demo observation report.",
                {
                    "candidate_name": {"type": "string"},
                    "mission_mode": {"type": "string"},
                    "purpose": {"type": "string"},
                },
                [],
                require_confirmation=True,
            ),
            "GenerateVisualSquadAndLineupBoard": _function_schema(
                "GenerateVisualSquadAndLineupBoard",
                "Save and render the proposed lineup and squad-risk board.",
                {
                    "board_mode": {"type": "string"},
                    "formation": {"type": "string"},
                    "demo_lineup": {"type": "boolean"},
                    "opponent": {"type": "string"},
                },
                [],
                require_confirmation=True,
            ),
        }
    return {
        "PlanMatchTactics": _function_schema(
            "PlanMatchTactics",
            "Save match context and recommend formation and playing style.",
            {
                "opponent": {"type": "string"},
                "squad_context": {"type": "string"},
                "available_budget_eur": {"type": "integer"},
                "preferred_style": {"type": "string"},
                "formation_options": {"type": "string"},
            },
            ["opponent", "squad_context"],
            require_confirmation=False,
        ),
        "SubmitPlayerSelectionToManagement": _function_schema(
            "SubmitPlayerSelectionToManagement",
            "Reserve budget and notify management after player selection.",
            {
                "candidate_name": {"type": "string"},
                "target_role": {"type": "string"},
                "salary_eur": {"type": "integer"},
                "selection_reason": {"type": "string"},
                "planning_context_id": {"type": "string"},
            },
            ["candidate_name", "target_role", "salary_eur"],
            require_confirmation=True,
        ),
        "FinalizeCurrentLineup": _function_schema(
            "FinalizeCurrentLineup",
            "Validate and save the finalized starting lineup.",
            {
                "formation": {"type": "string"},
                "lineup_json": {"type": "string"},
                "demo_lineup": {"type": "boolean"},
                "opponent": {"type": "string"},
                "planning_context_id": {"type": "string"},
            },
            [],
            require_confirmation=True,
        ),
        "GenerateCurrentLineupBoard": _function_schema(
            "GenerateCurrentLineupBoard",
            "Render the current lineup board as a private SVG.",
            {"lineup_id": {"type": "string"}},
            [],
            require_confirmation=False,
        ),
    }


def zip_final_lambda(folder: str) -> bytes:
    base = EXT / "lambdas" / folder
    common_dir = EXT / "lambdas" / "common"
    shared_dir = EXT / "lambdas" / "shared_football"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(base / "lambda_function.py", "lambda_function.py")
        for module in sorted(common_dir.glob("*.py")):
            zf.write(module, module.name)
        for module in sorted(shared_dir.glob("*.py")):
            zf.write(module, module.name)
    return buf.getvalue()


def patch_deployer(Deployer: type) -> None:
    def ensure_final_lambda_role(self, role_name: str, policy_doc: dict) -> str:
        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        try:
            role_arn = self.iam.get_role(RoleName=role_name)["Role"]["Arn"]
            self.present.append(f"IAM role exists: {role_name}")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchEntity":
                raise
            self.plan.append(f"Create IAM role: {role_name}")
            if not self.apply:
                return f"arn:aws:iam::{self.account_id}:role/{role_name}"
            role_arn = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust),
                Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
            )["Role"]["Arn"]
            time.sleep(10)
        self.plan.append(f"Update least-privilege inline policy: {role_name}")
        if self.apply:
            self.iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            )
            self.iam.put_role_policy(
                RoleName=role_name,
                PolicyName=f"{role_name}Inline",
                PolicyDocument=json.dumps(policy_doc),
            )
        return role_arn

    def _resolve_football_ops_storage(self) -> tuple[str, str, str]:
        ddb = self.session.client("dynamodb")
        try:
            ddb.describe_table(TableName=FOOTBALL_OPS_TABLE)
            self.present.append(f"Football ops table available: {FOOTBALL_OPS_TABLE}")
            return FOOTBALL_OPS_TABLE, "entity_key", ""
        except ClientError:
            self.present.append(
                f"Football ops table unavailable; using isolated prefix in {FOOTBALL_OPS_TABLE_FALLBACK}"
            )
            return (
                FOOTBALL_OPS_TABLE_FALLBACK,
                FOOTBALL_OPS_HASH_KEY_FALLBACK,
                FOOTBALL_OPS_KEY_PREFIX_FALLBACK,
            )

    def _ddb_table_arn(self, table_name: str) -> str:
        return f"arn:aws:dynamodb:{REGION}:{self.account_id}:table/{table_name}"

    def _sns_topic_arn(self) -> str:
        return f"arn:aws:sns:{REGION}:{self.account_id}:{SNS_TOPIC_NAME}"

    def _lineup_prefix_arn(self, bucket: str) -> list[str]:
        return [
            f"arn:aws:s3:::{bucket}",
            f"arn:aws:s3:::{bucket}/{LINEUP_S3_PREFIX}*",
        ]

    def ensure_final_lambda(self, name: str, folder: str, role_arn: str) -> str:
        zip_bytes = zip_final_lambda(folder)
        try:
            fn = self.lambda_client.get_function(FunctionName=name)
            self.present.append(f"Lambda exists: {name}")
            if self.apply:
                self.lambda_client.update_function_code(FunctionName=name, ZipFile=zip_bytes)
                self.plan.append(f"Updated Lambda code: {name}")
            return fn["Configuration"]["FunctionArn"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
        self.plan.append(f"Create Lambda: {name}")
        if not self.apply:
            return f"arn:aws:lambda:{REGION}:{self.account_id}:function:{name}"
        resp = self.lambda_client.create_function(
            FunctionName=name,
            Runtime="python3.12",
            Role=role_arn,
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zip_bytes},
            Timeout=30,
            MemorySize=256,
            Publish=True,
            Tags=TAGS,
        )
        self._wait_lambda_active(name)
        return resp["FunctionArn"]

    def detach_action_group(self, agent_id: str, action_group_name: str) -> None:
        self.plan.append(f"Detach action group from agent (Lambda preserved): {action_group_name}")
        if not self.apply:
            return
        groups = self.agent.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT").get(
            "actionGroupSummaries", []
        )
        existing = next((g for g in groups if g.get("actionGroupName") == action_group_name), None)
        if not existing:
            self.present.append(f"Action group already absent: {action_group_name}")
            return
        detail = self.agent.get_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=existing["actionGroupId"],
        )["agentActionGroup"]
        self.agent.update_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=existing["actionGroupId"],
            actionGroupName=action_group_name,
            actionGroupState="DISABLED",
            actionGroupExecutor=detail.get("actionGroupExecutor", {}),
            functionSchema=detail.get("functionSchema", {}),
            description=detail.get("description", action_group_name),
        )
        self.present.append(f"Detached action group: {action_group_name}")

    def upload_kb_tactical_documents(self, bucket: str, kb_id: str, ds_id: str) -> None:
        self.plan.append(f"Upload additive tactical KB documents under {KB_TACTICAL_PREFIX}")
        if not self.apply:
            return
        s3 = self.session.client("s3")
        for path in sorted(KB_DOCS.glob("*.txt")):
            key = f"{KB_TACTICAL_PREFIX}{path.name}"
            s3.put_object(Bucket=bucket, Key=key, Body=path.read_bytes(), ContentType="text/plain")
            self.present.append(f"Uploaded KB doc: {key}")
        try:
            self.agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
            self.present.append("Started Knowledge Base ingestion sync for tactical documents")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConflictException":
                self.blockers.append(f"KB ingestion start failed: {exc}")

    def apply_final_four_architecture(self, agent_id: str, agent_arn: str, bucket: str, kb_id: str, ds_id: str) -> None:
        self.log("\n=== FINAL FOUR-LAMBDA ARCHITECTURE ===")
        self.ensure_dynamodb_table(FOOTBALL_OPS_TABLE, hash_key="entity_key")
        ops_table, ops_hash_key, ops_prefix = self._resolve_football_ops_storage()
        sns_arn = self.ensure_sns_topic()
        self.plan.append(plan_demo_roster_seed())
        if self.apply and ops_table == FOOTBALL_OPS_TABLE:
            result = apply_demo_roster_seed(table_name=FOOTBALL_OPS_TABLE, apply=True)
            self.present.append(f"Demo roster seed: {result.get('status')}")
        elif self.apply:
            self.present.append("Demo roster seed deferred (football-ops table fallback active)")

        self.upload_kb_tactical_documents(bucket, kb_id, ds_id)

        schemas = final_four_schemas()
        lambda_arns: dict[str, str] = {}
        for name, meta in FINAL_FOUR_LAMBDAS.items():
            role_name = meta["role"]
            if name == "ScoutMatchPlanMatchTacticsAvidan":
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:Scan",
                                "dynamodb:Query",
                            ],
                            "Resource": [self._ddb_table_arn(ops_table)],
                        }
                    ],
                }
            elif name == "ScoutMatchSubmitPlayerSelectionAvidan":
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:Scan",
                                "dynamodb:Query",
                            ],
                            "Resource": [self._ddb_table_arn(ops_table)],
                        },
                        {
                            "Effect": "Allow",
                            "Action": ["sns:Publish"],
                            "Resource": [sns_arn or self._sns_topic_arn()],
                        },
                    ],
                }
            elif name == "ScoutMatchFinalizeCurrentLineupAvidan":
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:Scan",
                                "dynamodb:Query",
                            ],
                            "Resource": [self._ddb_table_arn(ops_table)],
                        }
                    ],
                }
            else:
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:Scan",
                                "dynamodb:Query",
                            ],
                            "Resource": [self._ddb_table_arn(ops_table)],
                        },
                        {
                            "Effect": "Allow",
                            "Action": ["s3:PutObject", "s3:GetObject"],
                            "Resource": self._lineup_prefix_arn(bucket),
                        },
                    ],
                }
            role_arn = self.ensure_final_lambda_role(role_name, policy)
            lambda_arns[name] = self.ensure_final_lambda(name, meta["folder"], role_arn)
            if self.apply:
                env = {
                    "SCOUTMATCH_FOOTBALL_OPS_TABLE": ops_table,
                    "SCOUTMATCH_FOOTBALL_OPS_HASH_KEY": ops_hash_key,
                    "SCOUTMATCH_FOOTBALL_OPS_KEY_PREFIX": ops_prefix,
                    "SCOUTMATCH_DEMO_SEASON_ID": "opening-season-demo-v1",
                    "SCOUTMATCH_LINEUP_BUCKET": bucket,
                    "SCOUTMATCH_LINEUP_S3_PREFIX": LINEUP_S3_PREFIX,
                    "SCOUTMATCH_MANAGEMENT_SNS_TOPIC": SNS_TOPIC_NAME,
                    "SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN": sns_arn or "",
                }
                self.ensure_lambda_env(name, env)
                self.allow_agent_invoke(
                    name,
                    agent_arn,
                    f"bedrock-final-{agent_id}-{meta['action_group']}"[:80],
                )
                schema = schemas[meta["function"]]
                self.ensure_action_group(
                    agent_id,
                    lambda_arns[name],
                    meta["action_group"],
                    meta["function"],
                    meta["description"],
                    update_if_exists=True,
                    require_confirmation=meta["function"] in WRITE_CONFIRM_FUNCTIONS,
                )

        for group in ACTION_GROUPS_DETACHED_AT_FINAL_APPLY:
            self.detach_action_group(agent_id, group)

        self.plan.append("Preserve Agent Knowledge Base association (ENABLED, no disconnect)")
        self.plan.append("Final architecture: exactly 4 Action Groups, 4 dedicated Lambdas, 1 function each")
        self.present.append("Router Lambda excluded from final Agent-facing architecture")

        if self.apply:
            detail = self.agent.get_agent(agentId=agent_id)["agent"]
            update_kwargs: dict = {
                "agentId": agent_id,
                "agentName": detail["agentName"],
                "agentResourceRoleArn": detail["agentResourceRoleArn"],
                "foundationModel": detail.get("foundationModel")
                or "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
                "instruction": AGENT_INSTRUCTION_FINAL,
                "idleSessionTTLInSeconds": detail.get("idleSessionTTLInSeconds", 600),
            }
            guard = detail.get("guardrailConfiguration") or {}
            gid = str(self.state.get("guardrail_id") or guard.get("guardrailIdentifier") or "").strip()
            gver = str(self.state.get("guardrail_version") or guard.get("guardrailVersion") or "1").strip()
            if gid:
                update_kwargs["guardrailConfiguration"] = {
                    "guardrailIdentifier": gid,
                    "guardrailVersion": gver,
                }
            self.agent.update_agent(**update_kwargs)
            self.present.append("Updated agent instruction for final four-Lambda architecture")

    Deployer._ddb_table_arn = _ddb_table_arn
    Deployer._sns_topic_arn = _sns_topic_arn
    Deployer._lineup_prefix_arn = _lineup_prefix_arn
    Deployer._resolve_football_ops_storage = _resolve_football_ops_storage
    Deployer.ensure_final_lambda_role = ensure_final_lambda_role
    Deployer.ensure_final_lambda = ensure_final_lambda
    Deployer.detach_action_group = detach_action_group
    Deployer.upload_kb_tactical_documents = upload_kb_tactical_documents
    Deployer.apply_final_four_architecture = apply_final_four_architecture
