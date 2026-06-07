# ScoutMatch AI — Business Workflow V2

**Branch:** `feature/scoutmatch-business-workflow-v2`  
**Stable rollback branch:** `feature/scoutmatch-agent-flow-extension`  
**Feature flag:** `SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED` (default `false` on production until staging cutover)

## Product concept

ScoutMatch AI is an opening-season squad-building assistant for a football club that finished **fourth** last season and aims to **compete for the championship**. The primary user is the **Chief Scout / Recruitment Analyst**.

Human decision boundaries are explicit:

- The Agent may **recommend**; the scout **confirms** write actions.
- **Management** decides transfers; **technical director** decides sales; **head coach** reviews lineups.
- No player is signed, sold, or lineup-approved automatically.

## Four public Agent-facing tools (v2)

| Public tool | AWS Lambda (name preserved) | Action Group |
|-------------|----------------------------|--------------|
| `SubmitCriticalDecisionAndSendEmail` | `ScoutMatchSubmitPlayerSelectionAvidan` | `ScoutMatchCriticalDecisionActionsAvidan` |
| `OpenTransferOutReviewCase` | `ScoutMatchPlanMatchTacticsAvidan` | `ScoutMatchTransferOutActionsAvidan` |
| `CreateAndReviewScoutingMission` | `ScoutMatchFinalizeCurrentLineupAvidan` | `ScoutMatchScoutingMissionActionsAvidan` |
| `GenerateVisualSquadAndLineupBoard` | `ScoutMatchGenerateLineupBoardAvidan` | `ScoutMatchSquadBoardActionsAvidan` |

KB-grounded conversational answers (squad analysis, candidate comparison, budget) remain available **without** additional public tools.

## Feature flags

| Flag | Purpose |
|------|---------|
| `SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED` | Enables v2 tools, homepage, and workflow cards |
| `SCOUTMATCH_EMAIL_MODE` | `disabled` or `ses` (optional, non-blocking) |
| `SCOUTMATCH_CALENDAR_MODE` | `google_api`, `ics_fallback`, or `disabled` |
| `SCOUTMATCH_SCOUTING_REMINDER_MODE` | EventBridge Scheduler reminder (optional) |
| `SCOUTMATCH_DEMO_REPLAY_ENABLED` | Synthetic completed observation replay |

When v2 is disabled, the legacy four-tool opening-season flow remains active.

## DynamoDB record types

- `CRITICAL_DECISION_REVIEW` — `PENDING_MANAGEMENT_APPROVAL`
- `TRANSFER_OUT_REVIEW` — `PENDING_TECHNICAL_DIRECTOR_REVIEW`
- `SCOUTING_MISSION` — `PENDING_SCOUT_OBSERVATION` / `READY_FOR_RECRUITMENT_REVIEW`
- `PROPOSED_LINEUP` / `VISUAL_BOARD_METADATA` — `PENDING_HEAD_COACH_REVIEW`
- `BUDGET_LEDGER` — reservations with idempotency

Hypothetical transfer-out release amounts are **not** credited to active recruitment budget until technical-director approval.

## External integrations (optional)

- **Amazon SES:** review email after critical decision Confirm; never blocks DynamoDB writes.
- **Google Calendar API:** real events only when OAuth is configured; otherwise ICS fallback invite.
- **EventBridge Scheduler:** one-time reminder via existing scouting-mission Lambda (no fifth Lambda).

## Demo data

| Path | Content |
|------|---------|
| `sample_scout_data/season_context/` | Fourth place, championship objective, transfer window |
| `sample_scout_data/fixtures/` | Opening fixtures including Ron Ben Ari synthetic match |
| `sample_scout_data/completed_observations/` | Deterministic synthetic demo replay (Ron Ben Ari) |
| `sample_scout_data/demo_candidates/` | Ron Ben Ari, Tal Cohen profiles |
| `sample_scout_data/baseline/` | Legacy club documents (KB) |

## Rollback

- Docker rollback image: `scoutmatch-ai:baseline-club-v14`
- Set `SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED=false`
- Keep stable Agent alias on legacy four-tool Action Groups until v2 staging validation passes

## MCP wording

The project implements controlled tool use through Amazon Bedrock Agent Action Groups backed by AWS Lambda. It does **not** implement a standalone MCP server.

## Manual boundaries

1. Google OAuth consent and Calendar authorization
2. Amazon SES sender/recipient verification (sandbox)
3. Manual inbox and Calendar visual verification
4. Bedrock Agent v2 alias cutover on EC2 after staging passes
