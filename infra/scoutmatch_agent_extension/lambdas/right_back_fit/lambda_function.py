"""
ScoutMatchRightBackFitAvidan — EvaluateRightBackFit

Rules: coach_tactical_model.txt, fixture_congestion_note.txt, transfer_budget.txt
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
    qualitative_rating,
    require_bool,
    require_int,
    require_string,
)

ACTION_GROUP = "ScoutMatchRightBackActionsAvidan"
FUNCTION_NAME = "EvaluateRightBackFit"
RULE_SOURCES = [
    "coach_tactical_model.txt",
    "fixture_congestion_note.txt",
    "transfer_budget.txt",
]

MAX_COMBINED_EUR = 100_000
MAX_STANDARD_EUR = 60_000


def _budget_fits(annual_salary: int, committed: int) -> bool:
    return (committed + annual_salary) <= MAX_COMBINED_EUR and annual_salary <= MAX_STANDARD_EUR


def _evaluate(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    available_immediately = require_bool(params, "available_immediately")
    preferred_foot = require_string(params, "preferred_foot")
    build_up = require_string(params, "build_up_ability")
    crossing = require_string(params, "crossing_quality")
    overlap = require_string(params, "overlap_runs")
    annual_salary = require_int(params, "annual_salary_eur")
    committed = require_int(params, "current_committed_salary_eur")

    checks: dict[str, str] = {}
    reasons: list[str] = []
    negatives = 0
    unknowns = 0

    checks["immediate_availability"] = "PASS" if available_immediately else "PARTIAL"
    if not available_immediately:
        negatives += 1
        reasons.append(
            "Immediate availability is preferred during the congested fixture period."
        )

    foot = normalize_text(preferred_foot)
    if "right" in foot:
        checks["preferred_foot"] = "PASS"
    elif foot in {"", "unknown", "n/a"}:
        checks["preferred_foot"] = "UNKNOWN"
        unknowns += 1
        reasons.append("Preferred foot evidence is missing.")
    else:
        checks["preferred_foot"] = "PARTIAL"
        negatives += 1
        reasons.append("A right-footed player is preferred for the right-back role.")

    for label, value, key in (
        ("build_up_ability", build_up, "build_up_ability"),
        ("crossing_quality", crossing, "crossing_quality"),
        ("overlap_runs", overlap, "overlap_runs"),
    ):
        rating = qualitative_rating(value)
        if rating == "POSITIVE":
            checks[key] = "PASS"
        elif rating == "NEGATIVE":
            checks[key] = "FAIL"
            negatives += 1
            reasons.append(f"{label.replace('_', ' ')} does not meet the documented preference.")
        elif rating == "NEUTRAL":
            checks[key] = "PARTIAL"
            negatives += 1
            reasons.append(f"{label.replace('_', ' ')} is only partially evidenced.")
        else:
            checks[key] = "UNKNOWN"
            unknowns += 1
            reasons.append(f"{label.replace('_', ' ')} evidence is missing.")

    budget_ok = _budget_fits(annual_salary, committed)
    checks["salary_budget"] = "PASS" if budget_ok else "FAIL"
    if not budget_ok:
        negatives += 1
        reasons.append("Salary must fit the documented transfer budget.")

    if unknowns >= 2:
        decision = "UNKNOWN"
        reasons.append("Too many required tactical attributes are missing to decide.")
    elif negatives == 0 and unknowns == 0:
        decision = "PREFERRED_FIT"
        reasons.append("Candidate matches the documented right-back preferences.")
    elif negatives > 0 and budget_ok:
        decision = "PARTIAL_FIT"
    elif not budget_ok:
        decision = "FAIL"
    else:
        decision = "PARTIAL_FIT"

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
