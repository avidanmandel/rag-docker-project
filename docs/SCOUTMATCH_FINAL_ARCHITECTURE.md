# ScoutMatch Final Demo Architecture

## Main user role

The primary user is a **Scout / Recruitment Analyst / Professional Assistant**. They analyze squad needs from coach briefs, prepare player recommendations for management, and prepare proposed lineups for head-coach review.

## Business flow

1. Analyst receives coach updates and club evidence from the Bedrock Knowledge Base.
2. `PlanMatchTactics` analyzes urgent squad needs and proposes tactical options for the head coach.
3. `SubmitPlayerSelectionToManagement` reserves budget only after explicit confirmation and returns `PENDING_MANAGEMENT_APPROVAL`.
4. `FinalizeCurrentLineup` saves a proposed 11-player lineup only after confirmation and returns `PENDING_HEAD_COACH_REVIEW`.
5. `GenerateCurrentLineupBoard` renders a private SVG served through the Flask proxy route.

## AWS architecture

| Layer | Role |
|------|------|
| EC2 + Docker | Hosts polished root UI and Flask API on `0.0.0.0:80:5000` |
| Amazon Bedrock Agent | Orchestrates grounded conversation and tool selection |
| Amazon Bedrock Knowledge Base | Club tactical policies, CVs, scouting reports, budget rules |
| Central Guardrail | Blocks credentials and unauthorized system changes; VIOLENCE/MISCONDUCT/PROMPT_ATTACK input relaxed for football coach briefs (topic policy retains credential protection) |
| Four dedicated Lambdas | One function per Action Group |
| DynamoDB | Squad context, player selections, budget ledger, proposed lineups |
| SNS | Sanitized management notifications after confirmed selection |
| S3 | Private lineup SVG objects behind Flask proxy |

## Exact four Lambdas and Action Groups

| Function | Action Group | Lambda |
|----------|--------------|--------|
| `PlanMatchTactics` | `ScoutMatchTacticsActionsAvidan` | `ScoutMatchPlanMatchTacticsAvidan` |
| `SubmitPlayerSelectionToManagement` | `ScoutMatchSelectionAgAvidan` | `ScoutMatchSubmitPlayerSelectionAvidan` |
| `FinalizeCurrentLineup` | `ScoutMatchLineupActionsAvidan` | `ScoutMatchFinalizeCurrentLineupAvidan` |
| `GenerateCurrentLineupBoard` | `ScoutMatchLineupBoardActionsAvidan` | `ScoutMatchGenerateLineupBoardAvidan` |

## Confirmation safety

- Native Bedrock confirmation is enabled for selection and lineup write tools.
- Lambda-level confirmation checks remain as a second safety layer.
- Deny performs no DynamoDB write and no SNS publish.
- Confirm is idempotent and never claims management or head-coach approval.

## Rollback path

- Stable Docker image: `scoutmatch-ai:baseline-club-v14`
- Legacy helper Lambdas and Action Groups remain deployed for rollback only.
- Public alias ID remains stable for EC2 `.env.agent`.

## Demo flow

Use the polished root UI at `/` for the management presentation. Keep `/recruitment-advisor` as the diagnostic route only.
