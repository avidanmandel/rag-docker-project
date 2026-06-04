"""
ScoutMatchBudgetImpactAvidan — CalculateBudgetImpact

Rules source: sample_scout_data/baseline/transfer_budget.txt
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
    optional_string,
    require_bool,
    require_int,
    require_string,
)

ACTION_GROUP = "ScoutMatchBudgetActionsAvidan"
FUNCTION_NAME = "CalculateBudgetImpact"
RULE_SOURCES = ["transfer_budget.txt"]

MAX_COMBINED_EUR = 100_000
MAX_STANDARD_EUR = 60_000
MAX_EMERGENCY_EUR = 70_000


def _evaluate(params: dict, event: dict) -> dict:
    candidate_name = require_string(params, "candidate_name")
    candidate_salary = require_int(params, "candidate_annual_salary_eur")
    committed_before = require_int(params, "current_committed_salary_eur")
    immediate_starter = require_bool(params, "immediate_starter")
    justification = optional_string(params, "exception_justification")

    committed_after = committed_before + candidate_salary
    remaining = MAX_COMBINED_EUR - committed_after
    combined_ok = committed_after <= MAX_COMBINED_EUR
    standard_ok = candidate_salary <= MAX_STANDARD_EUR
    emergency_band = MAX_STANDARD_EUR < candidate_salary <= MAX_EMERGENCY_EUR

    reasons: list[str] = []
    decision = "FAIL"

    if not combined_ok:
        reasons.append(
            f"Combined committed salary {committed_after:,} EUR exceeds the maximum "
            f"{MAX_COMBINED_EUR:,} EUR for new signings."
        )
    elif candidate_salary > MAX_EMERGENCY_EUR:
        reasons.append(
            f"Salary {candidate_salary:,} EUR exceeds the emergency exception cap of "
            f"{MAX_EMERGENCY_EUR:,} EUR."
        )
    elif standard_ok and combined_ok:
        decision = "PASS"
        reasons.append(
            "Salary is within the standard single-player cap and the combined budget remains valid."
        )
    elif emergency_band and combined_ok and immediate_starter:
        decision = "NEEDS_EXCEPTION"
        reasons.append(
            "Salary is above the standard cap but within the documented emergency starter exception."
        )
        if not justification:
            reasons.append(
                "Exception justification should explain why an immediate starter needs up to 70,000 EUR."
            )
    elif emergency_band and combined_ok and not immediate_starter:
        reasons.append(
            "Emergency exception applies only to a clearly justified immediate starter."
        )
    elif candidate_salary > MAX_STANDARD_EUR:
        reasons.append(
            f"Salary {candidate_salary:,} EUR exceeds the standard cap of {MAX_STANDARD_EUR:,} EUR "
            "without a valid emergency exception."
        )

    body = {
        "candidate_name": candidate_name,
        "decision": decision,
        "candidate_salary_eur": candidate_salary,
        "committed_before_eur": committed_before,
        "committed_after_eur": committed_after,
        "remaining_budget_eur": max(remaining, 0),
        "combined_budget_check": "PASS" if combined_ok else "FAIL",
        "standard_single_player_cap_check": "PASS" if standard_ok else "FAIL",
        "emergency_exception_check": (
            "PASS"
            if decision == "NEEDS_EXCEPTION"
            else ("NOT_APPLICABLE" if standard_ok else "FAIL")
        ),
        "reasons": reasons,
        "rule_sources": RULE_SOURCES,
        "within_budget_statement": (
            "The proposal stays within the available budget."
            if decision == "PASS"
            else (
                "The proposal may stay within budget only if the emergency exception is approved."
                if decision == "NEEDS_EXCEPTION"
                else "The proposal does not stay within the documented budget rules."
            )
        ),
    }
    return build_function_response(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        body=body,
        event=event,
    )


def lambda_handler(event, context):  # noqa: ARG001
    return handle_action_errors(
        action_group=ACTION_GROUP,
        function_name=FUNCTION_NAME,
        event=event,
        handler=_evaluate,
    )
