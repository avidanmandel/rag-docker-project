"""
ScoutMatchForwardFitAvidan — EvaluateForwardFit

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
    qualitative_rating,
    require_bool,
    require_int,
    require_string,
)

ACTION_GROUP = "ScoutMatchForwardActionsAvidan"
FUNCTION_NAME = "EvaluateForwardFit"
RULE_SOURCES = [
    "coach_tactical_model.txt",
    "winter_window_priorities.txt",
    "transfer_budget.txt",
]

MAX_COMBINED_EUR = 100_000
FORWARD_SALARY_CAP_EUR = 50_000


def _evaluate(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    link_up = require_string(params, "link_up_play")
    movement = require_string(params, "movement")
    annual_salary = require_int(params, "annual_salary_eur")
    committed = require_int(params, "current_committed_salary_eur")
    exception_approved = require_bool(params, "exception_approved")

    checks: dict[str, str] = {}
    reasons: list[str] = []

    for label, value, key in (
        ("link_up_play", link_up, "link_up_play"),
        ("movement", movement, "movement"),
    ):
        rating = qualitative_rating(value)
        if rating == "POSITIVE":
            checks[key] = "PASS"
        elif rating == "NEGATIVE":
            checks[key] = "FAIL"
            reasons.append(f"{label.replace('_', ' ')} does not meet the documented forward requirement.")
        elif rating == "NEUTRAL":
            checks[key] = "PARTIAL"
            reasons.append(f"{label.replace('_', ' ')} is only partially evidenced.")
        else:
            checks[key] = "UNKNOWN"
            reasons.append(f"{label.replace('_', ' ')} evidence is missing.")

    combined_ok = (committed + annual_salary) <= MAX_COMBINED_EUR
    checks["combined_budget"] = "PASS" if combined_ok else "FAIL"
    if not combined_ok:
        reasons.append(
            f"Combined salary would exceed the maximum {MAX_COMBINED_EUR:,} EUR budget for new signings."
        )

    if annual_salary <= FORWARD_SALARY_CAP_EUR:
        checks["forward_salary_cap"] = "PASS"
        salary_ok = True
    elif exception_approved:
        checks["forward_salary_cap"] = "PASS"
        salary_ok = True
        reasons.append("Forward salary exception is marked as approved.")
    elif annual_salary > FORWARD_SALARY_CAP_EUR:
        checks["forward_salary_cap"] = "NEEDS_EXCEPTION"
        salary_ok = False
        reasons.append(
            f"Forward salary {annual_salary:,} EUR exceeds the documented {FORWARD_SALARY_CAP_EUR:,} EUR cap "
            "unless an exception is approved."
        )
    else:
        checks["forward_salary_cap"] = "UNKNOWN"
        salary_ok = False

    unknowns = sum(1 for v in checks.values() if v == "UNKNOWN")
    fails = sum(1 for v in checks.values() if v == "FAIL")

    if unknowns >= 2:
        decision = "UNKNOWN"
    elif fails or not combined_ok:
        decision = "FAIL"
    elif checks.get("forward_salary_cap") == "NEEDS_EXCEPTION":
        decision = "NEEDS_EXCEPTION"
    elif any(v == "UNKNOWN" for v in checks.values()):
        decision = "UNKNOWN"
    elif any(v == "PARTIAL" for v in checks.values()):
        decision = "PASS" if salary_ok and combined_ok else "NEEDS_EXCEPTION"
        reasons.append("Some forward attributes are only partially evidenced.")
    else:
        decision = "PASS"
        reasons.append("Candidate satisfies the documented forward recruitment policy.")

    if decision == "PASS" and not reasons:
        reasons.append("Candidate satisfies the documented forward recruitment policy.")

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
