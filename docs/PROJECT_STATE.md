# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Branch** | `feature/scoutmatch-agent-flow-extension` |
| **Public URL** | http://3.239.47.249/ |
| **Primary demo route** | `/` (polished root UI) |
| **Production image** | `scoutmatch-ai:agent-extension-v15` |
| **Rollback image** | `scoutmatch-ai:baseline-club-v14` |
| **Runtime** | `agent_extension_enabled=true`, `chat_backend=bedrock_agent` |
| **Last QA** | 2026-06-04 (UTC) |

## Production checks

| Check | Result |
|-------|--------|
| Public homepage | HTTP 200 |
| `/api/health` | HTTP 200 |
| `/api/status` | `ready=true` |
| Four-tool Agent architecture | Live validation BLOCKERS=0 |
| Automated tests | 437+ passed |
| Submission ZIP | READY_FOR_MANUAL_SCREENSHOTS |

## Architecture (current)

```
Browser → EC2 → Docker → Flask → Bedrock Agent → KB + Guardrail
  → 4 Action Groups → 4 dedicated Lambdas
  → DynamoDB operational state → private S3 lineup SVG → Flask proxy → inline board
```

Legacy helper Lambdas remain for rollback only and are **not** public Agent-facing tools.

## Notes

- Primary user persona: **Scout / Professional Analyst** (not Sporting Director).
- SNS is an optional future extension — not required for course submission.
- Baseline v14 screenshots: `submission_evidence/final_v14/`.
- Agent extension screenshots: `submission_evidence/agent_flow_extension/` (5 required).
- AWS cleanup deferred until post-submission approval (`docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md`).
