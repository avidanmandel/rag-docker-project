"""ScoutMatchBelowStrikerFitAvidan tests."""

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


below = _load_module("below_striker_lambda_function", "below_striker_fit")


def _invoke(**params):
    event = {"parameters": [{"name": k, "value": str(v)} for k, v in params.items()]}
    response = below.lambda_handler(event, None)
    return json.loads(response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])


def test_pass_tal_raz_profile():
    body = _invoke(
        candidate_name="Tal Raz",
        position="Attacking Midfielder",
        skill_scores="9,8,8",
        available_immediately=True,
        budget_info="52000,30000",
    )
    assert body["decision"] == "PASS"


def test_fail_low_scores():
    body = _invoke(
        candidate_name="Low Scores",
        position="Second Striker",
        skill_scores="7,8,8",
        available_immediately=True,
        budget_info="40000,20000",
    )
    assert body["decision"] == "FAIL"


def test_boundary_score_eight():
    body = _invoke(
        candidate_name="Boundary",
        position="Attacking midfielder",
        skill_scores="8,8,8",
        available_immediately=True,
        budget_info="40000,20000",
    )
    assert body["decision"] == "PASS"
    assert body["checks"]["vision_score"] == "PASS"
