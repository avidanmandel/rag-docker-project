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
    " Act as a sporting director assistant for ScoutMatch FC. Candidate recommendations must come from "
    "the attached Bedrock Knowledge Base evidence (static ScoutMatch documents, candidate reports, and "
    "club policy) plus dynamic DynamoDB planning context saved by UpdateSquadPlanningContext. If "
    "candidate evidence is missing or insufficient, ask for clarification instead of inventing a profile, "
    "salary, or management approval. Tactical fit helpers are internal only and are not user-facing tools. "
    "Remember opponent, formation, weak positions, operational budget, pending selections, and the latest "
    "lineup across follow-up messages in the same session. Resolve pronouns such as he, him, that player, "
    "and the right-back from prior context. When the sporting director chooses a player, call "
    "SubmitPlayerSelectionToManagement and require confirmation before any reservation or SNS notification. "
    "When the user asks to finalize the demo lineup, call FinalizeCurrentLineup with demo_lineup=true so "
    "the sanitized 4-3-3 roster with Ron Ben Ari at right-back is used. For non-demo lineups, require all "
    "11 starters explicitly and ask clarification instead of inventing players. When the user asks for the "
    "current lineup, call GenerateCurrentLineupBoard and return the safe image route. Distinguish static "
    "Knowledge Base policy from live operational budget and pending approval status."
)

# Runtime helpers invoked internally (not Agent-facing after simplified apply).
ACTIVE_INTERNAL_HELPERS_AT_RUNTIME = [
    "CalculateBudgetImpact",  # invoked by SubmitPlayerSelectionToManagement via ScoutMatchBudgetImpactAvidan
]

ROLLBACK_ONLY_INTERNAL_HELPERS = [
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

BUDGET_HELPER_LAMBDA_NAME = "ScoutMatchBudgetImpactAvidan"
BUDGET_HELPER_FUNCTION = "CalculateBudgetImpact"
