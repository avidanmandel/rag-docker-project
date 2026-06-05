# Four Dedicated Lambdas Summary

## 1. ScoutMatchPlanMatchTacticsAvidan — PlanMatchTactics

- Saves match planning context
- Recommends formation and playing style from documented rules + coach updates
- No budget reservation, no SNS, no lineup finalize
- Example outcome: **5-4-1** when full-backs are weak and striker can play alone

## 2. ScoutMatchSubmitPlayerSelectionAvidan — SubmitPlayerSelectionToManagement

- Resolves approved candidates only (Ron Ben Ari demo path)
- Uses shared packaged budget module (no Lambda invoke for budget math)
- Requires explicit confirmation before DynamoDB write and SNS publish
- Idempotent repeat confirm must not double-reserve
- Status: `PENDING_MANAGEMENT_APPROVAL`

## 3. ScoutMatchFinalizeCurrentLineupAvidan — FinalizeCurrentLineup

- Requires explicit confirmation
- Validates exactly 11 own-team starters
- Demo flow replaces Daniel Levy with Ron Ben Ari at right-back
- Preserves pending-management status

## 4. ScoutMatchGenerateLineupBoardAvidan — GenerateCurrentLineupBoard

- Reads latest finalized lineup
- Generates SVG with Python standard library only
- Writes private object under `scoutmatch/football-operations/lineups/`
- Returns safe Flask route `/api/recruitment-advisor/lineups/<lineup_id>/image`

## Live direct validation status

All four Lambdas: **PASS** (`validate_four_lambda_final.py`)
