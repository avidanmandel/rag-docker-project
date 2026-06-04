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


def _parse_budget_info(value: str) -> tuple[int, int]:
    parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError("budget_info must be annual_salary_eur,current_committed_salary_eur")
    return int(parts[0]), int(parts[1])


def _evaluate(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    available_immediately = require_bool(params, "available_immediately")
    preferred_foot = require_string(params, "preferred_foot")
    tactical_summary = require_string(params, "tactical_summary")
    annual_salary, committed = _parse_budget_info(require_string(params, "budget_info"))

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
    elif foot in {"unknown", "n/a", "na"}:
        checks["preferred_foot"] = "UNKNOWN"
        unknowns += 1
    else:
        checks["preferred_foot"] = "PARTIAL"
        negatives += 1
        reasons.append("A right-footed player is preferred for the right-back role.")

    rating = qualitative_rating(tactical_summary)
    if rating == "POSITIVE":
        checks["tactical_summary"] = "PASS"
    elif rating == "NEGATIVE":
        checks["tactical_summary"] = "FAIL"
        negatives += 1
        reasons.append("Tactical summary does not meet documented right-back preferences.")
    elif rating == "NEUTRAL":
        checks["tactical_summary"] = "PARTIAL"
        negatives += 1
    else:
        checks["tactical_summary"] = "UNKNOWN"
        unknowns += 1
        reasons.append("Tactical evidence is missing from the summary.")

    budget_ok = (committed + annual_salary) <= MAX_COMBINED_EUR and annual_salary <= MAX_STANDARD_EUR
    checks["salary_budget"] = "PASS" if budget_ok else "FAIL"
    if not budget_ok:
        negatives += 1
        reasons.append("Salary must fit the documented transfer budget.")

    if unknowns >= 2:
        decision = "UNKNOWN"
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
