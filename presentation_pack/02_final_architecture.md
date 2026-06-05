# Final Architecture

## Sporting Director flow

```
Sporting Director chat
  → Flask Recruitment Advisor
  → boto3 bedrock-agent-runtime.invoke_agent
  → Amazon Bedrock Agent (scoutmatch-recruitment-agent-user5-avidan)
  → central Guardrail (scoutmatch-guardrail-user5-avidan)
  → attached Knowledge Base (knowledge-base-user5, ENABLED)
  → four Action Groups
  → four dedicated Lambdas
  → DynamoDB operational state
  → SNS management notification
  → private S3 SVG lineup board
  → Flask image proxy route
```

## Static vs dynamic state

| Layer | Purpose |
|-------|---------|
| Knowledge Base | Club policies, CVs, scouting reports, tactical documents |
| DynamoDB | Opponent, budget, selection, lineup, pending approval status |

## Four Action Groups → four Lambdas → one function each

| Action Group | Lambda | Function |
|--------------|--------|----------|
| ScoutMatchTacticsActionsAvidan | ScoutMatchPlanMatchTacticsAvidan | PlanMatchTactics |
| ScoutMatchPlayerSelectionActionsAvidan | ScoutMatchSubmitPlayerSelectionAvidan | SubmitPlayerSelectionToManagement |
| ScoutMatchLineupActionsAvidan | ScoutMatchFinalizeCurrentLineupAvidan | FinalizeCurrentLineup |
| ScoutMatchLineupBoardActionsAvidan | ScoutMatchGenerateLineupBoardAvidan | GenerateCurrentLineupBoard |

## Preserved legacy resources (detached, not deleted)

- ScoutMatchNativeToolsAvidan
- ScoutMatchNativeActionsAvidan
- ScoutMatchFootballOperationsActionsAvidan
- Budget/fit helper Lambdas
- Shortlist / brief / workflow Lambdas and Step Functions

## Production split

- **v14 chat:** `boto3` Knowledge Base retrieve/generate
- **Advisor:** Bedrock Agent with tools and operational state
