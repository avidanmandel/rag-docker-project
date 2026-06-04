"""
ScoutMatchForwardFitAvidan — EvaluateForwardFit
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
    forward_profile = require_string(params, "forward_profile")
    annual_salary = require_int(params, "annual_salary_eur")
    committed = require_int(params, "current_committed_salary_eur")
    exception_approved = require_bool(params, "exception_approved")

    checks: dict[str, str] = {}
    reasons: list[str] = []

    rating = qualitative_rating(forward_profile)
    if rating == "POSITIVE":
        checks["forward_profile"] = "PASS"
    elif rating == "NEGATIVE":
        checks["forward_profile"] = "FAIL"
        reasons.append("Forward profile does not meet documented link-up and movement needs.")
    elif rating == "NEUTRAL":
        checks["forward_profile"] = "PARTIAL"
        reasons.append("Forward profile is only partially evidenced.")
    else:
        checks["forward_profile"] = "UNKNOWN"
        reasons.append("Forward profile evidence is missing.")

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
    else:
        checks["forward_salary_cap"] = "NEEDS_EXCEPTION"
        salary_ok = False
        reasons.append(
            f"Forward salary {annual_salary:,} EUR exceeds the documented {FORWARD_SALARY_CAP_EUR:,} EUR cap "
            "unless an exception is approved."
        )

    if checks.get("forward_profile") == "UNKNOWN":
        decision = "UNKNOWN"
    elif checks.get("forward_profile") == "FAIL" or not combined_ok:
        decision = "FAIL"
    elif checks.get("forward_salary_cap") == "NEEDS_EXCEPTION":
        decision = "NEEDS_EXCEPTION"
    elif checks.get("forward_profile") == "PARTIAL":
        decision = "PASS" if salary_ok and combined_ok else "NEEDS_EXCEPTION"
        reasons.append("Forward profile is only partially evidenced.")
    else:
        decision = "PASS"
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
