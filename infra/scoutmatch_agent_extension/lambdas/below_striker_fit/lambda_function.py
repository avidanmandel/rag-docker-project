"""
ScoutMatchBelowStrikerFitAvidan — EvaluateBelowStrikerFit

Rules: coach_tactical_model.txt, winter_window_priorities.txt, transfer_budget.txt
"""

from __future__ import annotations

import os
import sys

_LAMBDA_ROOT = os.path.dirname(os.path.abspath(__file__))
_COMMON = os.path.join(_LAMBDA_ROOT, os.pardir, "common")
if _COMMON not in sys.path:
    sys.path.insert(0, os.path.normpath(_COMMON))

from bedrock_response import (  # noqa: E402
    build_function_response,
    handle_action_errors,
    normalize_text,
    require_bool,
    require_int,
    require_string,
)

ACTION_GROUP = "ScoutMatchBelowStrikerActionsAvidan"
FUNCTION_NAME = "EvaluateBelowStrikerFit"
RULE_SOURCES = [
    "coach_tactical_model.txt",
    "winter_window_priorities.txt",
    "transfer_budget.txt",
]

MIN_SCORE = 8
MAX_COMBINED_EUR = 100_000
MAX_STANDARD_EUR = 60_000
ALLOWED_POSITIONS = (
    "attacking midfielder",
    "second striker",
    "attacking mid",
    "cam",
    "ss",
)


def _position_ok(position: str) -> bool:
    text = normalize_text(position)
    if not text:
        return False
    return any(token in text for token in ALLOWED_POSITIONS)


def _evaluate(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    position = require_string(params, "position")
    vision = require_int(params, "vision_score")
    creativity = require_int(params, "creativity_score")
    key_passing = require_int(params, "key_passing_score")
    available_immediately = require_bool(params, "available_immediately")
    annual_salary = require_int(params, "annual_salary_eur")
    committed = require_int(params, "current_committed_salary_eur")

    checks: dict[str, str] = {}
    reasons: list[str] = []

    if _position_ok(position):
        checks["position"] = "PASS"
    else:
        checks["position"] = "FAIL"
        reasons.append(
            "Position must be attacking midfielder or second striker for the role below the striker."
        )

    for label, score, key in (
        ("vision_score", vision, "vision_score"),
        ("creativity_score", creativity, "creativity_score"),
        ("key_passing_score", key_passing, "key_passing_score"),
    ):
        if score >= MIN_SCORE:
            checks[key] = "PASS"
        else:
            checks[key] = "FAIL"
            reasons.append(f"{label} must be at least {MIN_SCORE}.")

    checks["immediate_availability"] = "PASS" if available_immediately else "PARTIAL"
    if not available_immediately:
        reasons.append("Immediate availability is preferred for winter recruitment.")

    budget_ok = (committed + annual_salary) <= MAX_COMBINED_EUR and annual_salary <= MAX_STANDARD_EUR
    checks["salary_budget"] = "PASS" if budget_ok else "FAIL"
    if not budget_ok:
        reasons.append("Salary must fit the documented transfer budget.")

    failed = [k for k, v in checks.items() if v == "FAIL"]
    partial = [k for k, v in checks.items() if v == "PARTIAL"]

    if not position.strip():
        decision = "UNKNOWN"
        reasons.append("Position evidence is missing.")
    elif failed:
        decision = "FAIL"
    elif partial:
        decision = "PARTIAL_FIT"
        reasons.append("Candidate partially matches the documented below-striker requirements.")
    else:
        decision = "PASS"
        reasons.append("Candidate meets the documented below-striker requirements.")

    return build_function_response(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        body={
            "candidate_name": candidate_name,
            "decision": decision,
            "checks": checks,
            "reasons": reasons,
            "rule_sources": RULE_SOURCES,
        },
        event=event,
    )


def lambda_handler(event, context):  # noqa: ARG001
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        event=event,
        handler=_evaluate,
    )
