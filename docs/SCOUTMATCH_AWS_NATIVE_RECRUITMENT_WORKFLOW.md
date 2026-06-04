# ScoutMatch AWS-native recruitment workflow

## Architecture (AWS only)

```
Coach chat (optional Recruitment Advisor UI)
    → Amazon Bedrock Agent (scoutmatch-recruitment-agent-user5-avidan)
    → Action Group auto-selection
    → AWS Lambda
    → DynamoDB / S3 / Step Functions (as needed)
    → Agent natural-language reply
```

No outbound HTTP/HTTPS from extension Lambdas. Allowed SDK usage: `boto3` to DynamoDB, S3, Step Functions, and in-account Lambda invoke.

## Existing behavior preserved

- **RAG:** Knowledge Base `knowledge-base-user5` for club documents.
- **Four deterministic tools:** budget, right-back, below-striker, forward (unchanged handlers).
- **Guardrail:** `scoutmatch-guardrail-user5-avidan`.
- **v14 production path:** unchanged (`/api/chat`, EC2 Docker v14).

## New capabilities (after `--apply` approval)

### Shortlist (DynamoDB)

- Table: `ScoutMatchRecruitmentShortlistAvidan` (on-demand).
- Actions: add, list, update status, remove.
- Stores concise recruitment fields only — never raw CVs or secrets.

### Recruitment brief (S3)

- Prefix: `scoutmatch/recruitment-advisor/briefs/` in the configured `AWS_S3_BUCKET`.
- Actions: create, get latest, list summaries.
- Returns sanitized object keys only (no presigned URLs).

### Candidate review (Step Functions)

- State machine: `ScoutMatchCandidateReviewWorkflowAvidan`.
- Flow: validate → budget Lambda → role choice → tactical Lambda → save review → create brief.
- Workflow Lambda returns opaque `workflow_reference` tokens (not full ARNs).

## Agent conversation triggers

| Coach intent | Tool |
|--------------|------|
| Budget / salary what-if | `CalculateBudgetImpact` |
| Role fit | Tactical evaluate functions |
| “Add to shortlist” | Shortlist write (confirmation required) |
| “Run full review” | `StartCandidateReviewWorkflow` (confirmation required) |
| “Prepare staff brief” | `CreateRecruitmentBrief` (confirmation required) |
| Document facts | Knowledge Base retrieval |

## Write confirmation

Write actions require `sessionAttributes.write_confirmed=true` (or native Bedrock confirmation when enabled at apply time). Until confirmed, tools return `PENDING_CONFIRMATION` without mutating data.

## Least-privilege IAM (planned)

- Lambda role: DynamoDB limited to the two new tables; S3 limited to `scoutmatch/recruitment-advisor/briefs/*`.
- Step Functions role: invoke only ScoutMatch*Avidan Lambdas and PutItem on reviews table.
- Bedrock invoke permissions: `SourceArn` scoped to the new agent only.

## Demo conversations (post-apply)

1. “What is the maximum combined annual salary budget?” → KB + 100,000 EUR.
2. “Can we sign Example Player at 58,000 EUR with 35,000 committed?” → budget tool PASS.
3. “Add Ron Ben Ari to the right-back shortlist” → confirmation → shortlist saved.
4. “Run a full review for Or David as forward at 55,000 with 40,000 committed” → workflow → brief.
5. “Who is Donald Trump?” → refusal / no ScoutMatch football answer.

## Known limitations

- Step Functions status lookup against AWS executions is available only after apply deploys the state machine.
- Recruitment Advisor UI is **local optional**; not deployed to production EC2 in this stage.
- Experimental Bedrock aliases from IAM debugging remain; no automatic pruning.

## Unchanged production assets

- EC2 host, Docker v14 container, S3 baseline, KB documents — **not modified** by this plan.
