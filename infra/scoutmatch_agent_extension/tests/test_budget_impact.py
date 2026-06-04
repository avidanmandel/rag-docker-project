"""ScoutMatchBudgetImpactAvidan tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lambdas" / "common"))


def _load_budget_module():
    path = ROOT / "lambdas" / "budget_impact" / "lambda_function.py"
    spec = importlib.util.spec_from_file_location("budget_lambda_function", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


budget = _load_budget_module()


def _invoke(**params):
    event = {"parameters": [{"name": k, "value": str(v)} for k, v in params.items()]}
    response = budget.lambda_handler(event, None)
    return json.loads(response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def test_budget_pass_within_standard_cap():
    body = _invoke(
        candidate_name="Example Player",
        candidate_annual_salary_eur=58000,
        current_committed_salary_eur=35000,
        immediate_starter=False,
    )
    assert body["decision"] == "PASS"
    assert body["combined_budget_check"] == "PASS"


def test_budget_fail_combined_exceeded():
    body = _invoke(
        candidate_name="Example Player",
        candidate_annual_salary_eur=70000,
        current_committed_salary_eur=50000,
        immediate_starter=True,
        exception_justification="Urgent starter",
    )
    assert body["decision"] == "FAIL"
    assert body["combined_budget_check"] == "FAIL"


def test_budget_needs_exception_emergency_path():
    body = _invoke(
        candidate_name="Starter",
        candidate_annual_salary_eur=68000,
        current_committed_salary_eur=20000,
        immediate_starter=True,
    )
    assert body["decision"] == "NEEDS_EXCEPTION"


def test_budget_fail_above_emergency_cap():
    body = _invoke(
        candidate_name="Over Cap",
        candidate_annual_salary_eur=75000,
        current_committed_salary_eur=10000,
        immediate_starter=True,
    )
    assert body["decision"] == "FAIL"


def test_missing_parameter_reprompt():
    event = {"parameters": [{"name": "candidate_name", "value": "X"}]}
    response = budget.lambda_handler(event, None)
    assert response["response"]["functionResponse"]["responseState"] == "REPROMPT"


def test_invalid_integer_reprompt():
    event = {
        "parameters": [
            {"name": "candidate_name", "value": "X"},
            {"name": "candidate_annual_salary_eur", "value": "not-a-number"},
            {"name": "current_committed_salary_eur", "value": "0"},
            {"name": "immediate_starter", "value": "true"},
        ]
    }
    response = budget.lambda_handler(event, None)
    assert response["response"]["functionResponse"]["responseState"] == "REPROMPT"
