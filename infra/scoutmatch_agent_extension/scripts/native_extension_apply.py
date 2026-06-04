"""AWS-native extension apply helpers (imported by deploy_scoutmatch_extension)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

WRITE_CONFIRM_FUNCTIONS = {
    "AddCandidateToShortlist",
    "UpdateCandidateShortlistStatus",
    "RemoveCandidateFromShortlist",
    "CreateRecruitmentBrief",
    "StartCandidateReviewWorkflow",
}

NATIVE_TOOLS_ROLE = "ScoutMatchNativeToolsLambdaRoleAvidan"
NATIVE_WORKFLOW_ROLE = "ScoutMatchNativeWorkflowRoleAvidan"


def _function_schema_with_confirmation(
    schema_fn,
    function_name: str,
    description: str,
    properties: dict,
    required: list[str],
    *,
    require_confirmation: bool,
) -> dict:
    fn = schema_fn(function_name, description, properties, required)
    if require_confirmation:
        fn["requireConfirmation"] = "ENABLED"
    else:
        fn["requireConfirmation"] = "DISABLED"
    return fn


def build_state_machine_definition(
    *,
    region: str,
    account_id: str,
    reviews_table: str,
    brief_function: str,
) -> dict[str, Any]:
    """Standard workflow using Bedrock-shaped Lambda payloads (no HTTPS tasks)."""
    _ = account_id
    return {
        "Comment": "ScoutMatch candidate review — AWS services only",
        "StartAt": "CalculateBudgetImpact",
        "States": {
            "CalculateBudgetImpact": {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": "ScoutMatchBudgetImpactAvidan",
                    "Payload": {
                        "actionGroup": "ScoutMatchBudgetActionsAvidan",
                        "function": "CalculateBudgetImpact",
                        "parameters.$": "$.budgetParameters",
                    },
                },
                "ResultPath": "$.budgetResult",
                "Retry": [
                    {
                        "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
                        "IntervalSeconds": 2,
                        "MaxAttempts": 2,
                        "BackoffRate": 2,
                    }
                ],
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.error",
                        "Next": "WorkflowFailed",
                    }
                ],
                "Next": "SelectRole",
            },
            "SelectRole": {
                "Type": "Choice",
                "Choices": [
                    {
                        "Variable": "$.target_role_normalized",
                        "StringEquals": "right-back",
                        "Next": "EvaluateRightBackFit",
                    },
                    {
                        "Variable": "$.target_role_normalized",
                        "StringEquals": "below-striker",
                        "Next": "EvaluateBelowStrikerFit",
                    },
                    {
                        "Variable": "$.target_role_normalized",
                        "StringEquals": "forward",
                        "Next": "EvaluateForwardFit",
                    },
                ],
                "Default": "RejectUnknownRole",
            },
            "EvaluateRightBackFit": {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": "ScoutMatchRightBackFitAvidan",
                    "Payload.$": "$.rightBackPayload",
                },
                "ResultPath": "$.tacticalResult",
                "Next": "ReturnResult",
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.error",
                        "Next": "WorkflowFailed",
                    }
                ],
            },
            "EvaluateBelowStrikerFit": {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": "ScoutMatchBelowStrikerFitAvidan",
                    "Payload.$": "$.belowStrikerPayload",
                },
                "ResultPath": "$.tacticalResult",
                "Next": "ReturnResult",
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.error",
                        "Next": "WorkflowFailed",
                    }
                ],
            },
            "EvaluateForwardFit": {
                "Type": "Task",
                "Resource": "arn:aws:states:::lambda:invoke",
                "Parameters": {
                    "FunctionName": "ScoutMatchForwardFitAvidan",
                    "Payload.$": "$.forwardPayload",
                },
                "ResultPath": "$.tacticalResult",
                "Next": "ReturnResult",
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.error",
                        "Next": "WorkflowFailed",
                    }
                ],
            },
            "RejectUnknownRole": {
                "Type": "Fail",
                "Error": "UnsupportedRole",
                "Cause": "target_role is not supported",
            },
            "ReturnResult": {
                "Type": "Pass",
                "Parameters": {
                    "workflow_status": "SUCCEEDED",
                    "candidate_name.$": "$.candidate_name",
                    "target_role.$": "$.target_role",
                    "budgetResult.$": "$.budgetResult",
                    "tacticalResult.$": "$.tacticalResult",
                },
                "End": True,
            },
            "WorkflowFailed": {
                "Type": "Pass",
                "Parameters": {"workflow_status": "FAILED"},
                "End": True,
            },
        },
    }
