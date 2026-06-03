# ScoutMatch AI — Agent Guide

## Project

Session-scoped RAG football recruitment assistant. Production runs on EC2 with Docker, Amazon Bedrock Knowledge Base, and S3.

## Branch and release

- **Branch:** `feature/session-scoped-documents`
- **Production image:** `scoutmatch-ai:baseline-club-v14` (rollback: `baseline-club-v13`)
- **Public URL:** http://3.239.47.249/
- **EC2 release folder:** `/home/ubuntu/scoutmatch-ai-session-docs-release`
- **Runtime mount:** `/home/ubuntu/scoutmatch-ai-runtime:/app/runtime`

## Key files

| File | Role |
|------|------|
| `app.py` | Flask API, upload parsing, session routes |
| `aws_kb_engine.py` | Bedrock retrieve/generate, aggregate answers |
| `aws_storage_service.py` | S3 upload, KB sync |
| `database.py` | SQLite sessions, documents, parsed upload facts |
| `requirement_verification.py` | Deterministic fact parsing and aggregate builders |
| `scripts/full_live_validation_matrix.py` | Strict live validation (use `--strict`) |
| `scripts/deploy_baseline_club_v14.sh` | EC2 deploy and cutover for v14 |
| `scripts/final_targeted_preflight.py` | Focused v14 public/candidate validation |
| `scripts/seed_baseline_club_knowledge.py` | Seed read-only club knowledge to S3 |

## Rules for agents

- Do **not** commit `.env`, PEM keys, `chat.db`, or `artifacts/logs/`.
- Do **not** use local Docker Desktop for production images; build on EC2.
- Use disposable sessions and synthetic documents for live validation.
- Shell scripts must use **LF** line endings (see `.gitattributes`).
- Cut over production only when strict validation reports `BLOCKERS 0`.
- Do **not** delete Bedrock KB, terminate EC2, or run destructive AWS cleanup without explicit approval.

## Validation commands

```bash
# Local
python -m pytest tests/test_scoutmatch.py -q --tb=no
python scripts/validate_release_fixtures.py
bash scripts/run_edge_case_release_matrix.sh

# EC2 loopback candidate (no production impact)
bash scripts/run_edge_case_release_matrix.sh

# Full deploy + cutover
bash scripts/deploy_baseline_club_v14.sh
```

## Documentation

See `docs/PROJECT_STATE.md`, `docs/DEPLOYMENT_RUNBOOK.md`, and `docs/FINAL_QA_REPORT.md`.
