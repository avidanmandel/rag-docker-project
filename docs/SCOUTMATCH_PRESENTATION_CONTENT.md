# ScoutMatch Presentation Content (six slides)

Use this outline to build the course deck. **No final PPTX is committed** in this repository as of 2026-06-04.

## 1. About Me

- Student: Avidan (user5 course environment)
- Project: ScoutMatch AI — football recruitment assistant
- Focus: grounded RAG + optional dynamic sporting-director workflow

## 2. Project Overview

- **Problem:** Small clubs need evidence-based recruitment without hallucinated player facts.
- **Primary user:** Scout / Recruitment Analyst / Professional Assistant (not the head coach).
- **Solution:** Upload CVs and club documents → Bedrock Knowledge Base → polished root UI with Bedrock Agent orchestration and strict source validation.
- **Workflow:** Analyst prepares recommendations for management (`PENDING_MANAGEMENT_APPROVAL`) and proposed lineups for head-coach review (`PENDING_HEAD_COACH_REVIEW`).

## 3. Technologies Used

- Python, Flask, boto3
- Amazon S3, Bedrock Knowledge Base, Bedrock Agent, Lambda
- DynamoDB (operational state), SNS (management alerts), Step Functions (optional workflow)
- Docker on Amazon EC2
- SQLite (v14 sessions/uploads only)

## 4. System Architecture

**Polished root UI (final demo)**

```
Browser → EC2 Docker → Flask → bedrock-agent-runtime invoke_agent
  → Agent + central Guardrail + Knowledge Base (ENABLED)
  → 4 Action Groups (1 Tool each) → 4 dedicated Lambdas
  → DynamoDB operational state / private S3 SVG / SNS
```

| Lambda | Tool |
|--------|------|
| `ScoutMatchPlanMatchTacticsAvidan` | `PlanMatchTactics` |
| `ScoutMatchSubmitPlayerSelectionAvidan` | `SubmitPlayerSelectionToManagement` |
| `ScoutMatchFinalizeCurrentLineupAvidan` | `FinalizeCurrentLineup` |
| `ScoutMatchGenerateLineupBoardAvidan` | `GenerateCurrentLineupBoard` |

Static policy and reports: **Knowledge Base**. Live opponent, budget, selections, lineups: **DynamoDB**.

## 5. Live Demo

- Public grounded budget question with sources
- Barcelona 4-3-3 context, Ron Ben Ari selection, confirmation, reservation
- Inline SVG lineup board with pending-management badge
- Unsupported question refusal

See `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md`.

## 6. Challenges and Next Steps

- **Challenges:** Bedrock Action Group quota → four dedicated Lambdas (no router); separating static KB from dynamic DynamoDB state; confirmation/idempotency for budget and lineup writes; IAM limits on dedicated football-ops table.
- **Next steps:** Capture dynamic console screenshots; optional public EC2 Advisor cutover (`scripts/deploy_recruitment_advisor_ec2.sh`); manual SNS email subscription; optional Advisor history persistence; cleanup after explicit approval (`docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md`).

## PPTX status

| Item | Status |
|------|--------|
| Final `.pptx` in repository | **Not found** |
| Slide content ready | **Yes** (this file) |
| Reflects current architecture | **Yes** (four-tool simplified design) |
