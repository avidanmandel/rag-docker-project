import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
os.environ["SCOUTMATCH_WORKFLOW_INPROCESS"] = "true"
_LAMBDA = Path(__file__).resolve().parents[1] / "lambdas" / "recruitment_workflow"
_COMMON = _LAMBDA.parent / "common"
for path in (str(_COMMON), str(_LAMBDA)):
    if path not in sys.path:
        sys.path.insert(0, path)
_spec = importlib.util.spec_from_file_location(
    "scoutmatch_workflow_lambda", _LAMBDA / "lambda_function.py"
)
workflow = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(workflow)


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def _event(function, params, confirmed=False):
    return {
        "function": function,
        "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
        "sessionAttributes": {"write_confirmed": "true"} if confirmed else {},
    }


@pytest.fixture(autouse=True)
def clear_state():
    workflow._LOCAL_REVIEWS.clear()
    workflow._LOCAL_STATUS.clear()
    yield
    workflow._LOCAL_REVIEWS.clear()
    workflow._LOCAL_STATUS.clear()


def test_right_back_workflow_branch():
    started = _body(
        workflow.lambda_handler(
            _event(
                "StartCandidateReviewWorkflow",
                {
                    "candidate_name": "Ron Ben Ari",
                    "target_role": "right-back",
                    "candidate_salary_eur": "58000",
                    "current_committed_salary_eur": "35000",
                    "immediate_starter": "true",
                },
                confirmed=True,
            ),
            None,
        )
    )
    assert started["status"] == "STARTED"
    ref = started["workflow_reference"]
    assert "arn:aws" not in ref
    status = _body(
        workflow.lambda_handler(
            _event("GetCandidateReviewWorkflowStatus", {"workflow_reference": ref}),
            None,
        )
    )
    assert status["workflow_status"] == "SUCCEEDED"
    result = _body(
        workflow.lambda_handler(
            _event("GetCandidateReviewResult", {"candidate_name": "Ron Ben Ari"}),
            None,
        )
    )
    assert result["status"] == "FOUND"
    assert result["review"]["budget_decision"] in {"PASS", "NEEDS_EXCEPTION", "FAIL"}


def test_unknown_role_rejected():
    resp = workflow.lambda_handler(
        _event(
            "StartCandidateReviewWorkflow",
            {
                "candidate_name": "Unknown",
                "target_role": "goalkeeper",
                "candidate_salary_eur": "50000",
                "current_committed_salary_eur": "0",
                "immediate_starter": "false",
            },
            confirmed=True,
        ),
        None,
    )
    assert _body(resp)["status"] == "REJECTED"


def test_missing_data_rejected():
    resp = workflow.lambda_handler(
        _event(
            "StartCandidateReviewWorkflow",
            {"candidate_name": "Example Player", "target_role": "forward"},
            confirmed=True,
        ),
        None,
    )
    assert _body(resp)["status"] == "FAILURE"
