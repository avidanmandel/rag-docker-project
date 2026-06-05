# Verified Project Facts

Audit date: 2026-06-05 (read-only pre-manual preparation)

## Repository

- Branch: `feature/scoutmatch-agent-flow-extension`
- Latest pushed implementation commit: `2faee6f`
- Production stable image: `scoutmatch-ai:baseline-club-v14`
- Public production URL: http://3.239.47.249/

## Final architecture (verified in AWS read-only audit)

- Agent: `scoutmatch-recruitment-agent-user5-avidan` — **found**, status **PREPARED**
- Knowledge Base: `knowledge-base-user5` — **attached**, association **ENABLED**
- Four final Action Groups enabled on agent DRAFT view
- Four dedicated Lambdas exist
- Legacy Action Groups detached from agent-facing config
- Legacy Lambdas preserved (native router, budget/fit helpers)
- KB tactical ingestion: **COMPLETE** (4 tactical objects in S3 prefix)
- Private lineup S3 prefix accessible with sample objects present

## Operational storage (verified via Lambda configuration)

- Dedicated table `ScoutMatchFootballOperationsAvidan`: create/describe not confirmed from workstation IAM
- Active fallback: `ScoutMatchRecruitmentShortlistAvidan`
- Key prefix: `football_ops#`
- Hash key: `candidate_key`

## Not yet verified on production EC2

- Public `/recruitment-advisor` route
- EC2 image `scoutmatch-ai:agent-extension-v15`
- Browser inline SVG demo on public host

## Local verification

- Extension tests: 80 passed
- v14 tests: 256 passed
- Full suite: 366 passed, 2 pre-existing soak failures
- Live Lambda/agent validation: `BLOCKERS=0`

## Manual still required

- EC2 safe cutover
- SNS email subscription (list/create denied from local IAM during audit)
- Console guardrail attachment verification (named guardrail exists; agent version attachment not confirmed by API read)
- Screenshot capture
- Submission ZIP
