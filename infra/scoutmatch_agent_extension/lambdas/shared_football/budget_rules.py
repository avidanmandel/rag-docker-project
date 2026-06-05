"""Shared packaged budget rules (no Lambda invoke)."""

from __future__ import annotations

MAX_COMBINED_EUR = 100_000
MAX_STANDARD_EUR = 60_000
MAX_EMERGENCY_EUR = 70_000
RULE_SOURCES = ["transfer_budget.txt"]


def evaluate_budget(
    *,
    candidate_name: str,
    candidate_salary: int,
    committed_before: int,
    immediate_starter: bool = True,
    justification: str = "",
) -> dict:
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
        reasons.append("Emergency exception applies only to a clearly justified immediate starter.")
    elif candidate_salary > MAX_STANDARD_EUR:
        reasons.append(
            f"Salary {candidate_salary:,} EUR exceeds the standard cap of {MAX_STANDARD_EUR:,} EUR "
            "without a valid emergency exception."
        )

    return {
        "candidate_name": candidate_name,
        "decision": decision,
        "candidate_salary_eur": candidate_salary,
        "committed_before_eur": committed_before,
        "committed_after_eur": committed_after,
        "remaining_budget_eur": max(remaining, 0),
        "reasons": reasons,
        "rule_sources": RULE_SOURCES,
    }
