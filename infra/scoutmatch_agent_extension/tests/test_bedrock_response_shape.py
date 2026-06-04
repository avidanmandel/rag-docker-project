"""Bedrock Action Group response shape tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "lambdas" / "common"
sys.path.insert(0, str(COMMON))

from bedrock_response import (  # noqa: E402
    MESSAGE_VERSION,
    ParameterError,
    build_failure,
    build_function_response,
    build_reprompt,
    handle_action_errors,
    parse_function_parameters,
    require_bool,
    require_int,
)


def test_parse_function_parameters_from_list():
    event = {
        "parameters": [
            {"name": "candidate_name", "value": "Example Player"},
            {"name": "candidate_annual_salary_eur", "value": "58000"},
        ]
    }
    params = parse_function_parameters(event)
    assert params["candidate_name"] == "Example Player"
    assert params["candidate_annual_salary_eur"] == "58000"


def test_bedrock_function_response_shape():
    event = {"sessionAttributes": {"session": "abc"}}
    response = build_function_response(
        action_group="ScoutMatchBudgetActionsAvidan",
        function_name="CalculateBudgetImpact",
        body={"decision": "PASS"},
        event=event,
    )
    assert response["messageVersion"] == MESSAGE_VERSION
    body = response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
    assert json.loads(body)["decision"] == "PASS"
    assert response["sessionAttributes"] == {"session": "abc"}


def test_reprompt_state():
    response = build_reprompt(
        action_group="G",
        function_name="F",
        message="Missing candidate_name",
        event={},
    )
    assert response["response"]["functionResponse"]["responseState"] == "REPROMPT"


def test_failure_state():
    response = build_failure(
        action_group="G",
        function_name="F",
        message="Error",
        event={},
    )
    assert response["response"]["functionResponse"]["responseState"] == "FAILURE"


def test_require_bool_invalid():
    with pytest.raises(ParameterError):
        require_bool({"flag": "maybe"}, "flag")


def test_handle_action_errors_reprompt():
    def handler(_params, _event):
        require_int({}, "missing")

    response = handle_action_errors(
        action_group="G",
        function_name="F",
        event={},
        handler=handler,
    )
    assert response["response"]["functionResponse"]["responseState"] == "REPROMPT"
