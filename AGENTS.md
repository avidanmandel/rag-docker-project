# ScoutMatch AI — Agent Guide

## Project

Opening-season football recruitment workspace for **Scouts / Professional Analysts**. Production runs on EC2 with Docker, Amazon Bedrock Knowledge Base, and optional Bedrock Agent extension (four-tool architecture).

## Branch and release

- **Branch:** `feature/scoutmatch-agent-flow-extension`
- **Production image:** `scoutmatch-ai:agent-extension-v15` (rollback: `scoutmatch-ai:baseline-club-v14`)
- **Public URL:** http://3.239.47.249/
- **Primary demo route:** `/` (root polished UI)
- **Diagnostic route only:** `/recruitment-advisor`
- **EC2 release folder:** `/home/ubuntu/scoutmatch-ai-session-docs-release`
- **Runtime mount:** `/home/ubuntu/scoutmatch-ai-runtime:/app/runtime`

## Key files

| File | Role |
|------|------|
| `app.py` | Flask API, upload parsing, session routes |
| `bedrock_agent_service.py` | Bedrock Agent integration for root UI |
| `aws_kb_engine.py` | Bedrock retrieve/generate, aggregate answers |
| `aws_storage_service.py` | S3 upload, KB sync |
| `database.py` | SQLite sessions, documents, parsed upload facts |
| `scripts/validate_public_production_gate.py` | Sanitized public production checks |
| `scripts/prepare_submission_zip.py` | Submission ZIP with forbidden-file validation |
| `scripts/final_course_readiness_rehearsal.py` | Live rehearsal A–G |

## Rules for agents

- Do **not** commit `.env`, `.env.agent`, PEM keys, `chat.db`, `infra/**/.local/`, or `artifacts/logs/`.
- Do **not** package repair helpers (`fix_agent_model.py`, `repair_agent_runtime.py`) in submission ZIP.
- Treat **SNS as optional only** — not a course blocker.
- Do **not** use local Docker Desktop for production images; build on EC2.
- Shell scripts must use **LF** line endings (see `.gitattributes`).
- Do **not** delete Bedrock KB, terminate EC2, or run destructive AWS cleanup without explicit approval.

## Validation commands

```bash
python -m pytest -q
python scripts/validate_public_production_gate.py
python scripts/final_course_readiness_rehearsal.py
python scripts/prepare_submission_zip.py
python scripts/run_secret_scan.py
```

## Documentation

See `docs/SCOUTMATCH_FINAL_COURSE_READINESS_REPORT.md`, `docs/SCOUTMATCH_SUBMISSION_ZIP_MANIFEST.md`, and `docs/SCOUTMATCH_SUBMISSION_READINESS_REPORT.md`.
