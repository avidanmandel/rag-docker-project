"""ScoutMatchRightBackFitAvidan tests."""

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


rb = _load_module("right_back_lambda_function", "right_back_fit")


def _invoke(**params):
    event = {"parameters": [{"name": k, "value": str(v)} for k, v in params.items()]}
    response = rb.lambda_handler(event, None)
    return json.loads(response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def test_preferred_fit():
    body = _invoke(
        candidate_name="Ron Ben Ari",
        available_immediately=True,
        preferred_foot="Right",
        build_up_ability="Good build-up",
        crossing_quality="Accurate crossing",
        overlap_runs="Strong overlapping runs",
        annual_salary_eur=45000,
        current_committed_salary_eur=30000,
    )
    assert body["decision"] == "PREFERRED_FIT"


def test_partial_fit_delayed_availability():
    body = _invoke(
        candidate_name="Delayed RB",
        available_immediately=False,
        preferred_foot="Right",
        build_up_ability="Good",
        crossing_quality="Accurate",
        overlap_runs="Strong",
        annual_salary_eur=45000,
        current_committed_salary_eur=30000,
    )
    assert body["decision"] == "PARTIAL_FIT"


def test_unknown_missing_evidence():
    body = _invoke(
        candidate_name="Unknown Player",
        available_immediately=True,
        preferred_foot="unknown",
        build_up_ability="unknown",
        crossing_quality="unknown",
        overlap_runs="unknown",
        annual_salary_eur=45000,
        current_committed_salary_eur=30000,
    )
    assert body["decision"] == "UNKNOWN"
