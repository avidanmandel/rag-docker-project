"""Football operations apply helpers (imported by deploy_scoutmatch_extension)."""

from __future__ import annotations

FOOTBALL_OPS_TABLE = "ScoutMatchFootballOperationsAvidan"
SNS_TOPIC_NAME = "ScoutMatchManagementNotificationsAvidan"
LINEUP_S3_PREFIX = "scoutmatch/football-operations/lineups/"

FOOTBALL_OPS_WRITE_CONFIRM = frozenset(
    {
        "SubmitPlayerSelectionToManagement",
        "FinalizeCurrentLineup",
        "RecordPlayerAvailabilityChange",
    }
)

# Simplified course design: exactly four user-facing Agent Tools.
NATIVE_AGENT_FUNCTIONS_SIMPLIFIED = [
    "UpdateSquadPlanningContext",
    "SubmitPlayerSelectionToManagement",
    "FinalizeCurrentLineup",
    "GenerateCurrentLineupBoard",
]

# Backward-compatible alias used by deploy script imports.
NATIVE_AGENT_FUNCTIONS_V3 = list(NATIVE_AGENT_FUNCTIONS_SIMPLIFIED)

INTERNAL_AGENT_HELPERS = [
    "CalculateBudgetImpact",
    "EvaluateRightBackFit",
    "EvaluateBelowStrikerFit",
    "EvaluateForwardFit",
    "AddCandidateToShortlist",
    "ListShortlistCandidates",
    "RemoveCandidateFromShortlist",
    "StartCandidateReviewWorkflow",
    "GetCandidateReviewWorkflowStatus",
    "GetCandidateReviewResult",
    "CreateRecruitmentBrief",
    "GetRecruitmentBrief",
    "ListRecruitmentBriefs",
    "RecordPlayerAvailabilityChange",
    "AnalyzeSquadDepthGaps",
]

FOOTBALL_ACTION_GROUPS_DETACHED_AT_APPLY = [
    "ScoutMatchBudgetActionsAvidan",
    "ScoutMatchRightBackActionsAvidan",
    "ScoutMatchBelowStrikerActionsAvidan",
    "ScoutMatchForwardActionsAvidan",
]

NATIVE_AGENT_FUNCTIONS_REMOVED_FROM_AGENT = [
    "AddCandidateToShortlist",
    "StartCandidateReviewWorkflow",
    "ListShortlistCandidates",
    "RemoveCandidateFromShortlist",
    "CreateRecruitmentBrief",
    "GetRecruitmentBrief",
]

AGENT_INSTRUCTION_DYNAMIC_ADDENDUM = (
    " Act as a sporting director assistant for ScoutMatch FC. Use the Knowledge Base for static "
    "club policy and candidate reports, and use football-operations tools for dynamic DynamoDB state. "
    "Remember opponent, formation, weak positions, operational budget, pending selections, and the "
    "latest lineup across follow-up messages in the same session. Resolve pronouns such as he, him, "
    "that player, and the right-back from prior context. When the sporting director chooses a player, "
    "call SubmitPlayerSelectionToManagement and require confirmation before any reservation or SNS "
    "notification. Never invent salaries, players, or management approval. When the user asks for "
    "the current lineup, call GenerateCurrentLineupBoard and return the safe image route. Distinguish "
    "static Knowledge Base policy from live operational budget and pending approval status."
)
