# ScoutMatch AI — Agent Guide

## Project

Session-scoped RAG football recruitment assistant. Production runs on EC2 with Docker, Amazon Bedrock Knowledge Base, and S3.

## Branch and release

- **Branch:** `feature/session-scoped-documents`
- **Production image:** `scoutmatch-ai:session-docs-v10` (rollback: `session-docs-v9`)
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
| `scripts/deploy_session_docs_v10.sh` | Build, validate candidate, cutover |

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
bash scripts/run_strict_release_audit_v10.sh

# Full deploy + cutover
bash scripts/deploy_session_docs_v10.sh
```

## Documentation

See `docs/PROJECT_STATE.md`, `docs/DEPLOYMENT_RUNBOOK.md`, `docs/FINAL_QA_REPORT.md`, and `docs/AGENT_HANDOFF.md`.
