"""Approved opening-season business context for workflow v2."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_ROOT = REPO_ROOT / "sample_scout_data"

SEASON_SUMMARY = {
    "previous_season_finish": "4th place",
    "season_objective": "Compete for the championship",
    "transfer_window_status": "Open",
    "recruitment_budget_eur": 100_000,
    "opening_fixture_opponent": "Barcelona",
    "current_squad_count": 15,
    "candidate_pool_count": 8,
}

TRANSFER_OUT_PROFILES = {
    "daniel cohen": {
        "display_name": "Daniel Cohen",
        "position": "CM",
        "salary_eur": 32000,
        "expected_minutes": "limited",
        "rating": 72,
        "tactical_fit_summary": "Adequate but overlapping with other midfield options.",
        "squad_overlap_summary": "Competes with Noam Sharon, Ido Katz, and Eran Blum.",
        "estimated_budget_release_eur": 25000,
        "review_reason": "Limited expected minutes and squad overlap.",
    },
}

UPCOMING_FIXTURES = {
    "ron ben ari": {
        "candidate_name": "Ron Ben Ari",
        "fixture_name": "Ron Ben Ari's club vs. Hapoel City",
        "fixture_datetime": "2026-06-20T17:00:00+00:00",
        "display_date": "Saturday, 20:00",
        "source": "synthetic_demo_fixture",
    },
}

OBSERVATION_CHECKLIST_RB = [
    "Defensive positioning",
    "Overlapping runs",
    "Recovery speed",
    "Pressing intensity",
    "Decision-making under pressure",
]


def load_completed_observation_report(candidate_slug: str) -> dict | None:
    file_slug = candidate_slug.replace("-", "_")
    path = SAMPLE_ROOT / "completed_observations" / f"{file_slug}_completed_match_report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def business_context_cards() -> dict:
    return {
        **SEASON_SUMMARY,
        "transfer_window": SEASON_SUMMARY["transfer_window_status"],
        "current_squad": f"{SEASON_SUMMARY['current_squad_count']} players",
        "pre_scouted_candidates": f"{SEASON_SUMMARY['candidate_pool_count']}",
        "recruitment_budget": f"{SEASON_SUMMARY['recruitment_budget_eur']:,} EUR",
        "opening_fixture": SEASON_SUMMARY["opening_fixture_opponent"],
    }
