# ScoutMatch AWS-native workflow — gap analysis

## What already exists

- **ScoutMatch v14** strict-RAG Flask chat (`/api/chat`) with session uploads, Bedrock Knowledge Base retrieval, and deterministic aggregate builders.
- **Isolated Bedrock extension** on branch `feature/scoutmatch-agent-flow-extension`:
  - Agent `scoutmatch-recruitment-agent-user5-avidan` with Guardrail, shared read-only KB `knowledge-base-user5`, and **four deterministic football Action Groups**.
  - Flow `scoutmatch-recruitment-flow-user5-avidan` (Input → Agent alias → Output).
  - Four Lambdas: budget impact, right-back fit, below-striker fit, forward fit.
- **Runtime validation** (prior stage): Agent and Flow invoke succeed; budget KB answer returns **100,000 EUR**; guardrail blocks credentials and prompt attacks; tactical tools behave deterministically.

## Why the four existing tools remain valuable

They encode **documented club rules** (budget caps, tactical preferences, forward policy) without hallucination. The Agent should call them for salary what-if questions and role-fit decisions instead of inventing numbers or ratings.

## What is missing for a convincing AWS-native advisor

| Capability | Proposed AWS service | Namespaced resource |
|------------|---------------------|-------------------|
| Coach shortlist memory | DynamoDB | `ScoutMatchRecruitmentShortlistAvidan` |
| Staff-meeting brief archive | S3 prefix in existing bucket | `scoutmatch/recruitment-advisor/briefs/` |
| Full candidate review orchestration | Step Functions Standard | `ScoutMatchCandidateReviewWorkflowAvidan` |
| Review outcome store | DynamoDB | `ScoutMatchRecruitmentReviewsAvidan` |
| Agent tools (no manual Lambda pick) | Bedrock Action Groups | Shortlist, Brief, Workflow groups |

## Proposed resources (apply stage only)

- Lambdas: `ScoutMatchShortlistManagerAvidan`, `ScoutMatchRecruitmentBriefAvidan`, `ScoutMatchRecruitmentWorkflowAvidan`
- Action Groups: `ScoutMatchShortlistActionsAvidan`, `ScoutMatchRecruitmentBriefActionsAvidan`, `ScoutMatchRecruitmentWorkflowActionsAvidan`
- IAM: extend `ScoutMatchExtensionLambdaRoleAvidan` with table- and prefix-scoped inline policies; add `ScoutMatchExtensionWorkflowRoleAvidan` for Step Functions

## Stable resources (untouched)

- Production EC2, production Docker image `scoutmatch-ai:baseline-club-v14`
- Production S3 baseline objects and KB ingestion sources
- Existing Knowledge Base content and data source `scoutmatch-player-documents`
- Legacy demo agent/flow/Lambdas (`agent-quick-user5-avidan`, weather/time tools, etc.)
- v14 UI and `/api/chat` behavior

## Why no external API or scraping

Course and safety rules require **AWS-only** evidence chains. External football APIs would introduce network egress, licensing risk, and non-deterministic facts that conflict with the grounded KB + Lambda model.

## Adapter note (Step Functions)

Existing tactical Lambdas expect **Bedrock Action Group events**. Step Functions will pass the same JSON shape (see `lambdas/common/stepfn_adapter.py` and `step_functions/candidate_review.asl.json`). **No change** to the four existing Lambda handlers is required for Bedrock invocation.
