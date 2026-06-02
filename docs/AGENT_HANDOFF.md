# Agent Handoff — ScoutMatch AI

Last updated: 2026-06-02

## Current state

| Item | Value |
|------|-------|
| Branch | `feature/session-scoped-documents` |
| Production image | `scoutmatch-ai:baseline-club-v12` |
| Rollback | `scoutmatch-ai:session-docs-v11` |
| Baseline gate | **BLOCKERS 0** |
| EC2 | `ubuntu@3.239.47.249` |
| Checkout | `/home/ubuntu/scoutmatch-ai-session-docs-release` |

## v12 highlights

- Read-only **baseline club knowledge** in every conversation (`AWS_BASELINE_SET_ID=production`).
- Session-scoped **candidate uploads** unchanged from v11.
- Combined Bedrock retrieval filter: baseline OR active session.
- Deterministic multi-source answers (budget combo, below-striker, RB update lifecycle).
- UI sidebar: Club Knowledge (read-only) + Uploaded Candidate Documents.

## Validation

```bash
bash scripts/run_baseline_business_gate.sh   # loopback candidate
bash scripts/run_business_acceptance_gate.sh # v11 regression (baseline disabled)
python -m pytest tests/test_baseline_club_knowledge.py tests/test_scoutmatch.py -q
```

## Seed production baseline (after cutover)

```bash
sudo docker exec scoutmatch-ai python scripts/seed_baseline_club_knowledge.py --apply --baseline-set-id production
python scripts/audit_baseline_club_knowledge.py --dry-run
```

## Do not

- Run `aws_cleanup --apply` without explicit approval
- Modify screenshot PNG files via automation
- Delete Bedrock KB or terminate EC2 without approval
