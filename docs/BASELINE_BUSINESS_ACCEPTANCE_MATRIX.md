# Baseline Business Acceptance Matrix (v12)

Target image: `scoutmatch-ai:baseline-club-v12`  
Rollback: `scoutmatch-ai:session-docs-v11`

## Runner

```bash
IMAGE_TAG=scoutmatch-ai:baseline-club-v12 \
CANDIDATE=scoutmatch-ai-baseline-v12-candidate \
RUNTIME=/home/ubuntu/scoutmatch-ai-baseline-v12-runtime \
bash scripts/run_baseline_business_gate.sh
```

## Scopes

| Scope | S3 prefix | User actions |
|-------|-----------|--------------|
| Baseline club knowledge | `scoutmatch/knowledge-base/baseline/<set_id>/` | Read-only; visible in all sessions |
| Session candidates | `scoutmatch/knowledge-base/sessions/<session_id>/` | Upload, delete, clear, conversation delete |

## Mandatory categories

- BL-UI — Club Knowledge + Uploaded Candidate Documents sidebar
- BL-SEED — baseline seed dry-run / apply / idempotent
- BL-BASE — baseline-only questions (goal, urgent positions, availability, budget)
- BL-DEMO — demo candidate uploads and filters
- BL-MULTI — below-striker recommendation, budget combination
- BL-UPDATE — availability update changes RB recommendation
- BL-ISO — new session baseline + candidate isolation
- BL-REF — refusals and prompt injection
- BL-INV — invalid uploads (4xx, no side effects)
- BL-V11 — regression subset from v11 business gate

Cutover to production baseline (`AWS_BASELINE_SET_ID=production`) only when `BLOCKERS 0`.
