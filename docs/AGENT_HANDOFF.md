# Agent Handoff — ScoutMatch AI

Last updated: 2026-06-02

## Current state

| Item | Value |
|------|-------|
| Branch | `feature/session-scoped-documents` |
| Production image | `scoutmatch-ai:session-docs-v11` |
| Rollback | `scoutmatch-ai:session-docs-v10` |
| Business gate | **BLOCKERS 0** (v11, 2026-06-02) |
| EC2 | `ubuntu@3.239.47.249` |
| Release checkout | `/home/ubuntu/scoutmatch-ai-session-docs-release` |

## What was fixed (v11)

1. **Salary aggregate** — Quoted CSV salary fields parse correctly; total 471,000 EUR with unique player dedupe.
2. **Registry merge** — CV facts retained when scouting reports uploaded; unrelated fixtures excluded from player registry.
3. **Structured filters** — Left foot, defender relocation, GK compound, cheapest right back (EN + HE) are deterministic.
4. **Invalid uploads** — Corrupt/malformed files rejected at upload with friendly 4xx; no S3/DB/revision side effects.

## Business acceptance gate

Run on EC2 loopback candidate (does not change production until cutover):

```bash
IMAGE_TAG=scoutmatch-ai:session-docs-v11 \
CANDIDATE=scoutmatch-ai-v11-business-gate-candidate \
RUNTIME=/home/ubuntu/scoutmatch-ai-v11-business-gate-runtime \
bash scripts/run_business_acceptance_gate.sh
grep '^BLOCKERS ' /tmp/business_gate_v11_iter3.log
```

Must show `BLOCKERS 0` before production cutover.

## Next work (deferred)

- **Baseline club knowledge** — not started; do not begin until explicitly requested.

## Do not

- Print or commit secrets (`.env`, PEM, DB contents)
- Run `aws_cleanup --apply` or terminate EC2 without explicit approval
- Modify screenshot PNG files or run screenshot automation unless requested
- Cut over with `BLOCKERS > 0`

## Useful scripts

- Business gate: `scripts/run_business_acceptance_gate.sh`
- Checksum: `scripts/ec2_checksum_check.sh`
- AWS cleanup dry-run: `scripts/aws_cleanup_dry_run.sh`
