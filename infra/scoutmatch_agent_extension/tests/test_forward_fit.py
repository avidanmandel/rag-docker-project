"""ScoutMatchForwardFitAvidan tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lambdas" / "common"))


def _load_module(name: str, folder: str):
    path = ROOT / "lambdas" / folder / "lambda_function.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


forward = _load_module("forward_lambda_function", "forward_fit")


def _invoke(**params):
    event = {"parameters": [{"name": k, "value": str(v)} for k, v in params.items()]}
    response = forward.lambda_handler(event, None)
    return json.loads(response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def test_or_david_pass_with_exception():
    body = _invoke(
        candidate_name="Or David",
        link_up_play="Excellent link-up play",
        movement="Strong movement",
        annual_salary_eur=58000,
        current_committed_salary_eur=30000,
        exception_approved=True,
    )
    assert body["decision"] == "PASS"


def test_forward_needs_exception_salary():
    body = _invoke(
        candidate_name="Expensive Forward",
        link_up_play="Good link-up",
        movement="Good movement",
        annual_salary_eur=58000,
        current_committed_salary_eur=30000,
        exception_approved=False,
    )
    assert body["decision"] == "NEEDS_EXCEPTION"


def test_forward_pass_under_cap():
    body = _invoke(
        candidate_name="Budget Forward",
        link_up_play="Good link-up play",
        movement="Strong movement",
        annual_salary_eur=48000,
        current_committed_salary_eur=30000,
        exception_approved=False,
    )
    assert body["decision"] == "PASS"
