import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["SCOUTMATCH_USE_LOCAL_STORE"] = "true"
_LAMBDA = Path(__file__).resolve().parents[1] / "lambdas" / "recruitment_brief"
_COMMON = _LAMBDA.parent / "common"
for path in (str(_COMMON), str(_LAMBDA)):
    if path not in sys.path:
        sys.path.insert(0, path)
_spec = importlib.util.spec_from_file_location(
    "scoutmatch_brief_lambda", _LAMBDA / "lambda_function.py"
)
brief = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(brief)


def _body(resp):
    return json.loads(resp["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def _event(function, params, confirmed=False):
    return {
        "function": function,
        "parameters": [{"name": k, "value": str(v)} for k, v in params.items()],
        "sessionAttributes": {"write_confirmed": "true"} if confirmed else {},
    }


@pytest.fixture(autouse=True)
def clear_store():
    brief._LOCAL_STORE.clear()
    yield
    brief._LOCAL_STORE.clear()


def test_create_requires_confirmation():
    resp = brief.lambda_handler(
        _event(
            "CreateRecruitmentBrief",
            {
                "candidate_name": "Or David",
                "target_role": "forward",
                "tactical_decision": "PASS",
                "budget_decision": "PASS",
            },
        ),
        None,
    )
    assert _body(resp)["status"] == "PENDING_CONFIRMATION"


def test_create_get_list_brief():
    brief.lambda_handler(
        _event(
            "CreateRecruitmentBrief",
            {
                "candidate_name": "Or David",
                "target_role": "forward",
                "tactical_decision": "PASS",
                "budget_decision": "PASS",
            },
            confirmed=True,
        ),
        None,
    )
    got = _body(brief.lambda_handler(_event("GetRecruitmentBrief", {"candidate_name": "Or David"}), None))
    assert got["status"] == "FOUND"
    assert "object_key" in got["brief"]
    assert "scoutmatch/recruitment-advisor/briefs/" in got["brief"]["object_key"]
    listed = _body(brief.lambda_handler(_event("ListRecruitmentBriefs", {}), None))
    assert listed["count"] == 1


def test_no_presigned_url_or_secrets():
    resp = brief.lambda_handler(
        _event(
            "CreateRecruitmentBrief",
            {
                "candidate_name": "Tal Raz",
                "target_role": "below-striker",
                "tactical_decision": "PASS",
                "budget_decision": "PASS",
            },
            confirmed=True,
        ),
        None,
    )
    text = json.dumps(_body(resp))
    assert "presigned" not in text.lower()
    assert "AKIA" not in text
