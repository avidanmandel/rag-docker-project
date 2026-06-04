# ScoutMatch AWS-native recruitment workflow

## Architecture (AWS only — applied)

```
Coach chat (Recruitment Advisor UI or Bedrock console)
    → Amazon Bedrock Agent (scoutmatch-recruitment-agent-user5-avidan)
    → Action Group auto-selection (football tools + native tools)
    → AWS Lambda (boto3 only — no outbound HTTP/HTTPS)
    → DynamoDB / S3 / Step Functions
    → Agent natural-language reply
```

**Applied on branch** `feature/scoutmatch-agent-flow-extension` (stage two). Production EC2, Docker v14, S3 baseline, and Knowledge Base documents were **not** modified.

## Existing behavior preserved

- **RAG:** Knowledge Base `knowledge-base-user5` for club documents.
- **Four deterministic football Action Groups** (unchanged): budget, right-back, below-striker, forward.
- **Guardrail:** `scoutmatch-guardrail-user5-avidan`.
- **v14 production path:** unchanged (`/api/chat`, EC2 Docker v14).

## Applied AWS-native resources

| Resource | Name | Notes |
|----------|------|--------|
| DynamoDB shortlist | `ScoutMatchRecruitmentShortlistAvidan` | On-demand; demo rows only |
| DynamoDB reviews | `ScoutMatchRecruitmentReviewsAvidan` | Sanitized review JSON + workflow ref index |
| Lambda shortlist | `ScoutMatchShortlistManagerAvidan` | Direct validation; not on agent (quota) |
| Lambda brief | `ScoutMatchRecruitmentBriefAvidan` | Direct validation; not on agent (quota) |
| Lambda workflow | `ScoutMatchRecruitmentWorkflowAvidan` | Direct validation; not on agent (quota) |
| Lambda native router | `ScoutMatchNativeToolsAvidan` | Single Action Group for agent (6 APIs) |
| Step Functions | `ScoutMatchCandidateReviewWorkflowAvidan` | Standard; no HTTPS tasks |
| Agent Action Group | `ScoutMatchNativeActionsAvidan` | Shortlist + brief + workflow starts (quota-safe) |
| IAM Lambda role | `ScoutMatchNativeToolsLambdaRoleAvidan` | DDB, S3 brief prefix, SFN start/describe |
| IAM SFN role | `ScoutMatchNativeWorkflowRoleAvidan` | Invoke ScoutMatch*Avidan Lambdas only |

### Bedrock 10-API quota consolidation

The agent allows **10 enabled APIs**. Four football groups use four APIs; the native extension uses **one** consolidated group (`ScoutMatchNativeActionsAvidan`) with six write/read tools:

- `AddCandidateToShortlist`, `ListShortlistCandidates`, `RemoveCandidateFromShortlist`
- `CreateRecruitmentBrief`, `GetRecruitmentBrief`
- `StartCandidateReviewWorkflow`

`UpdateCandidateShortlistStatus`, `ListRecruitmentBriefs`, `GetCandidateReviewWorkflowStatus`, and `GetCandidateReviewResult` remain on the standalone Lambdas for direct/tests only.

## Shortlist (DynamoDB)

- Table: `ScoutMatchRecruitmentShortlistAvidan`.
- Stores concise recruitment fields only — never raw CVs, secrets, or full ARNs.

## Recruitment brief (S3)

- Bucket: configured `AWS_S3_BUCKET` (Avidan-owned `oz-bucket-user5`).
- Prefix: `scoutmatch/recruitment-advisor/briefs/`.
- **No empty placeholder object** — keys appear only after confirmed brief creation or workflow finalization.
- Returns sanitized `object_key` only (no presigned URLs).

## Candidate review (Step Functions)

- State machine: `ScoutMatchCandidateReviewWorkflowAvidan`.
- Path: `CalculateBudgetImpact` → `SelectRole` → tactical Lambda → `ReturnResult`.
- Review persistence and S3 brief generation run in `ScoutMatchRecruitmentWorkflowAvidan` when status is polled (workflow-internal confirmation; no duplicate coach prompts).
- UI receives opaque `workflow_reference` tokens (e.g. `review-…`), not execution ARNs.

## Write confirmation

- **Primary:** Bedrock native confirmation (`requireConfirmation=ENABLED`) on write functions in `ScoutMatchNativeActionsAvidan`.
- **Secondary:** `sessionAttributes.write_confirmed=true` for direct Lambda tests and workflow-internal brief writes.
- Read actions do not require confirmation.

## Live validation (stage two)

| Check | Result |
|-------|--------|
| Direct shortlist add / deny without confirm | SAVED / PENDING_CONFIRMATION |
| Step Functions workflow + status poll | SUCCEEDED |
| Agent: right-back + budget follow-up | PASS |
| Agent: shortlist deny (no write) | PASS |
| Flow budget question | 100,000 EUR PASS |
| S3 prefix | Objects only after writes |

Script: `python infra/scoutmatch_agent_extension/scripts/validate_stage2_native.py` (results in gitignored `.local/stage2_validation.json`).

## Demo records (manual review — do not auto-delete)

- Shortlist: `DEMO Ron Ben Ari`, `DEMO Agent Deny Only` (if agent confirm test ran), direct-test entries.
- Reviews: `demo wf3`, `demo wf4`, workflow keys `workflow#review-…`.
- S3 briefs under `scoutmatch/recruitment-advisor/briefs/demo-*`.

## Known limitations

- Agent alias quota (10 per agent): existing alias updated to latest prepared version instead of creating new aliases.
- Flow version quota (10): draft Agent node synced; alias routing may be unchanged until quota frees.
- Deploy user may lack DynamoDB `DescribeTable` / `Scan` — tables created; Lambdas use scoped IAM.
- `UpdateCandidateShortlistStatus` not exposed on agent; use remove + add if needed.

## Unchanged production assets

- EC2 host, Docker v14 container, S3 baseline, KB documents — **not modified**.
