# ScoutMatch RAG recommendation safety

## Preserved association (do not disconnect at apply)

| Resource | Value |
|----------|-------|
| Agent | `scoutmatch-recruitment-agent-user5-avidan` |
| Knowledge Base | `knowledge-base-user5` |
| Association state | **ENABLED** (preserved, not disconnected) |

Stable v14 continues to use direct Knowledge Base retrieval via Flask (`aws_kb_engine.py`). The Recruitment Advisor uses `bedrock-agent-runtime` `invoke_agent` with the same KB attached to the Agent.

## Where candidate recommendations come from

| Source | Role |
|--------|------|
| Bedrock Knowledge Base | Grounded evidence from static ScoutMatch S3 documents |
| Candidate reports | Indexed KB documents for approved demo candidates |
| Club policy documents | Budget and recruitment policy in KB |
| DynamoDB planning context | Live opponent, formation, priorities, operational budget from `UpdateSquadPlanningContext` |

The Agent must **not** invent candidate profiles, salaries, or management approval.

## Safe behavior when evidence is missing

- Ask for clarification or state that evidence is insufficient.
- Do not invent a candidate profile.
- Do not invent salary values.
- Do not invent final management approval (`PENDING_MANAGEMENT_APPROVAL` only from DynamoDB writes).

## Internal helpers at runtime (honest report)

### Active after simplified apply

| Helper | Lambda | How it runs |
|--------|--------|-------------|
| `CalculateBudgetImpact` | `ScoutMatchBudgetImpactAvidan` | Invoked internally by `SubmitPlayerSelectionToManagement` via `boto3` `lambda:InvokeFunction` (least-privilege IAM on `ScoutMatchNativeToolsAvidan`) |

### Rollback-only (not Agent-facing after simplified apply)

These Lambdas remain deployed for rollback and direct tests but are **not** exposed as user-facing Agent Tools:

- `EvaluateRightBackFit` (`ScoutMatchRightBackFitAvidan`)
- `EvaluateBelowStrikerFit` (`ScoutMatchBelowStrikerFitAvidan`)
- `EvaluateForwardFit` (`ScoutMatchForwardFitAvidan`)
- Shortlist, workflow, brief, availability, and squad-depth helpers

Detached football Action Groups are **not** used by the Agent for recommendations after apply. Tactical fit is conveyed through KB evidence and sporting-director conversation, not through direct Agent tool calls.

## Exactly four user-facing Agent Tools

1. `UpdateSquadPlanningContext`
2. `SubmitPlayerSelectionToManagement`
3. `FinalizeCurrentLineup`
4. `GenerateCurrentLineupBoard`

`CalculateBudgetImpact` is **not** user-facing.
