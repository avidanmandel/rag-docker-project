"""
Opening-season workspace metadata for ScoutMatch AI.

Deterministic fictional demo data — no real-player information.
"""

from __future__ import annotations

from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent
DATASET_ROOT = (
    ROOT / "infra" / "scoutmatch_agent_extension" / "demo_data" / "opening_season"
)
DEMO_SEASON_ID = "opening-season-demo-v1"
S3_NAMESPACE = "scoutmatch/knowledge-base/opening-season/v1"

CLUB_PLAYER_COUNT = 15
STARTING_PLAYER_COUNT = 11
ROTATION_PLAYER_COUNT = 4
CANDIDATE_POOL_COUNT = 8

V2_SUGGESTED_PROMPTS = [
    {
        "label": "Which current player should we consider selling to free budget for a new right-back?",
        "query": (
            "We need to free budget for a new right-back. "
            "Which current player should we consider selling?"
        ),
    },
    {
        "label": "Create a scouting mission for Ron Ben Ari's next match and add it to my calendar.",
        "query": (
            "Ron Ben Ari looks promising. "
            "Create a scouting mission for his next match and add it to my calendar."
        ),
    },
    {
        "label": "Show me Ron Ben Ari's completed scouting report.",
        "query": "Show me Ron Ben Ari's completed scouting report.",
    },
    {
        "label": (
            "I choose Ron Ben Ari as our right-back candidate. "
            "Submit the recommendation for management review."
        ),
        "query": (
            "I choose Ron Ben Ari as our right-back candidate. "
            "Submit the recommendation for management review."
        ),
    },
    {
        "label": "Show me the updated proposed lineup and squad-risk board.",
        "query": "Show me the updated proposed lineup and squad-risk board.",
    },
]

V2_HERO = {
    "headline": "Build the strongest squad for the season.",
    "subtitle": (
        "Review the squad, open transfer-out cases, schedule scouting missions, "
        "submit critical decisions, and shape the lineup before the transfer window closes."
    ),
}

V2_BUSINESS_CARDS = [
    {"label": "Last season", "value": "4th place"},
    {"label": "Season objective", "value": "Compete for the championship"},
    {"label": "Transfer window", "value": "Open"},
    {"label": "Current squad", "value": "15 players"},
    {"label": "Pre-scouted candidates", "value": "8"},
    {"label": "Recruitment budget", "value": "100,000 EUR"},
    {"label": "Opening fixture", "value": "Barcelona"},
]


LEGACY_SUGGESTED_PROMPTS = [
    {
        "label": "Analyze our current squad weaknesses before the opening match.",
        "query": (
            "Analyze our current squad weaknesses before the opening match. "
            "Use the current club squad and squad depth analysis."
        ),
    },
    {
        "label": "Compare the right-back candidates within our budget.",
        "query": (
            "Compare the right-back candidates within our recruitment budget. "
            "Include Ron Ben Ari and Tal Cohen."
        ),
    },
    {
        "label": (
            "The coach reported that our starting goalkeeper is injured. "
            "Prepare a goalkeeper replacement plan."
        ),
        "query": (
            "Coach brief: Our starting goalkeeper was injured during training and will miss "
            "the next three matches. Which position should we prioritize and what tactical "
            "adjustment should we propose to the head coach?"
        ),
    },
    {
        "label": "Recommend a formation for the opening match based on our current squad.",
        "query": (
            "Recommend a formation for the opening match based on our current 15-player squad, "
            "tactical principles, and known depth weaknesses."
        ),
    },
]


def active_suggested_prompts() -> list[dict]:
    if config.SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED:
        return V2_SUGGESTED_PROMPTS
    return LEGACY_SUGGESTED_PROMPTS


SUGGESTED_PROMPTS = LEGACY_SUGGESTED_PROMPTS


SECONDARY_PROMPTS = [
    {
        "label": "Show the current proposed lineup.",
        "query": "Show me the current proposed lineup.",
    },
]

CLUB_KNOWLEDGE_DOCS = [
    {"display_name": "Opening-season storyline", "category": "Club Knowledge", "filename": "opening_season_storyline.md"},
    {"display_name": "Current club squad (15 players)", "category": "Squad", "filename": "current_club_squad.csv"},
    {"display_name": "Squad depth analysis", "category": "Squad", "filename": "squad_depth_analysis.md"},
    {"display_name": "Recruitment budget policy", "category": "Policy", "filename": "recruitment_budget_policy.md"},
    {"display_name": "Opening fixture brief", "category": "Fixtures", "filename": "opening_fixture_brief.md"},
    {"display_name": "Coach tactical principles", "category": "Tactics", "filename": "coach_tactical_principles.md"},
    {"display_name": "Demo prompt ground truth", "category": "Reference", "filename": "demo_prompt_ground_truth.md"},
]

CANDIDATE_POOL = [
    {
        "candidate_id": "cand-rb-ron",
        "name": "Ron Ben Ari",
        "primary_position": "Right-back",
        "salary_request": 43000,
        "profile_file": "candidates/ron_ben_ari_scouting_profile.md",
    },
    {
        "candidate_id": "cand-rb-tal",
        "name": "Tal Cohen",
        "primary_position": "Right-back",
        "salary_request": 38000,
        "profile_file": "candidates/tal_cohen_scouting_profile.md",
    },
    {
        "candidate_id": "cand-gk-omer",
        "name": "Omer Azulay",
        "primary_position": "Goalkeeper",
        "salary_request": 45000,
        "profile_file": "candidates/omer_azulay_scouting_profile.md",
    },
    {
        "candidate_id": "cand-gk-yossi",
        "name": "Yossi Levi",
        "primary_position": "Goalkeeper",
        "salary_request": 42000,
        "profile_file": "candidates/yossi_levi_scouting_profile.md",
    },
    {
        "candidate_id": "cand-cb-noam",
        "name": "Noam David",
        "primary_position": "Centre-back",
        "salary_request": 40000,
        "profile_file": "candidates/noam_david_scouting_profile.md",
    },
    {
        "candidate_id": "cand-cm-roy",
        "name": "Roy Cohen",
        "primary_position": "Midfielder",
        "salary_request": 39000,
        "profile_file": "candidates/roy_cohen_scouting_profile.md",
    },
    {
        "candidate_id": "cand-cm-miguel",
        "name": "Miguel Santos",
        "primary_position": "Midfielder",
        "salary_request": 37000,
        "profile_file": "candidates/miguel_santos_scouting_profile.md",
    },
    {
        "candidate_id": "cand-st-pedro",
        "name": "Pedro Silva",
        "primary_position": "Striker",
        "salary_request": 48000,
        "profile_file": "candidates/pedro_silva_scouting_profile.md",
    },
]


def dataset_files() -> list[Path]:
    files: list[Path] = []
    for rel in [
        "opening_season_storyline.md",
        "current_club_squad.csv",
        "squad_depth_analysis.md",
        "recruitment_candidate_pool.csv",
        "recruitment_budget_policy.md",
        "opening_fixture_brief.md",
        "coach_tactical_principles.md",
        "demo_prompt_ground_truth.md",
    ]:
        files.append(DATASET_ROOT / rel)
    for cand in CANDIDATE_POOL:
        files.append(DATASET_ROOT / cand["profile_file"])
    return [p for p in files if p.is_file()]


def club_knowledge_payload() -> list[dict]:
    return [
        {
            **doc,
            "scope": "opening_season",
            "read_only": True,
            "source": "preloaded",
        }
        for doc in CLUB_KNOWLEDGE_DOCS
    ]


def candidate_pool_payload() -> list[dict]:
    return [
        {
            **cand,
            "scope": "candidate_pool",
            "read_only": True,
            "recruitment_status": "pre-scouted",
            "display_name": cand["name"],
        }
        for cand in CANDIDATE_POOL
    ]


def workspace_summary() -> dict:
    summary = {
        "storyline": "opening_season",
        "demo_season_id": DEMO_SEASON_ID,
        "s3_namespace": S3_NAMESPACE,
        "club_player_count": CLUB_PLAYER_COUNT,
        "starting_player_count": STARTING_PLAYER_COUNT,
        "rotation_player_count": ROTATION_PLAYER_COUNT,
        "candidate_pool_count": CANDIDATE_POOL_COUNT,
        "club_knowledge_count": len(CLUB_KNOWLEDGE_DOCS),
        "workspace_ready": True,
        "suggested_prompts": active_suggested_prompts(),
        "secondary_prompts": SECONDARY_PROMPTS,
        "primary_user_role": "Chief Scout / Recruitment Analyst",
        "business_workflow_v2": config.SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED,
    }
    if config.SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED:
        summary["hero"] = V2_HERO
        summary["business_cards"] = V2_BUSINESS_CARDS
    return summary


def system_status_panel() -> dict:
    return {
        "club_knowledge": "available",
        "scouted_candidates": f"{CANDIDATE_POOL_COUNT} loaded",
        "agent_tools": "4 available",
        "safety_controls": "enabled",
        "chat_backend": "bedrock_agent",
        "knowledge_base": "connected",
        "guardrail": "attached",
    }
