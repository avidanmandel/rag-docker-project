"""
ScoutMatchBelowStrikerFitAvidan — EvaluateBelowStrikerFit
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


def _parse_scores(value: str) -> tuple[int, int, int]:
    parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 3:
        raise ValueError("skill_scores must be vision,creativity,key_passing")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _parse_budget_info(value: str) -> tuple[int, int]:
    parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError("budget_info must be annual_salary_eur,current_committed_salary_eur")
    return int(parts[0]), int(parts[1])


def _position_ok(position: str) -> bool:
    text = normalize_text(position)
    return any(token in text for token in ALLOWED_POSITIONS)


def _evaluate(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    position = require_string(params, "position")
    vision, creativity, key_passing = _parse_scores(require_string(params, "skill_scores"))
    available_immediately = require_bool(params, "available_immediately")
    annual_salary, committed = _parse_budget_info(require_string(params, "budget_info"))

    checks: dict[str, str] = {}
    reasons: list[str] = []

    checks["position"] = "PASS" if _position_ok(position) else "FAIL"
    if checks["position"] == "FAIL":
        reasons.append(
            "Position must be attacking midfielder or second striker for the role below the striker."
        )

    for label, score, key in (
        ("vision_score", vision, "vision_score"),
        ("creativity_score", creativity, "creativity_score"),
        ("key_passing_score", key_passing, "key_passing_score"),
    ):
        checks[key] = "PASS" if score >= MIN_SCORE else "FAIL"
        if score < MIN_SCORE:
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

    if failed:
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
