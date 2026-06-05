# ScoutMatch AI — Submission Checklist

Use before the lecturer submission ZIP. Cleanup remains **deferred** until screenshots, ZIP review, live demo, and explicit user approval.

## Required source files

- [ ] `app.py`
- [ ] `requirements.txt`
- [ ] `Dockerfile`
- [ ] `.dockerignore`
- [ ] `README.md`
- [ ] `templates/` and `static/`
- [ ] `aws_kb_engine.py`, `aws_storage_service.py`, `database.py`, `requirement_verification.py`
- [ ] `bedrock_agent_service.py`, `lineup_board_service.py` (Advisor extension)
- [ ] `sample_scout_data/`
- [ ] `infra/scoutmatch_agent_extension/` (Lambdas, deploy scripts, tests)
- [ ] `docs/` including `COURSE_REQUIREMENTS_COMPLIANCE_MATRIX.md`, `SCOUTMATCH_FINAL_DEMO_SCRIPT.md`
- [ ] `tests/test_scoutmatch.py`, `tests/test_bedrock_agent_advisor.py`, extension tests

## Exclude from ZIP

- [ ] `.env`, `.env.agent`, `.aws/`, `*.pem`, `*.key`
- [ ] `chat.db`, `runtime/`, `artifacts/logs/`, `__pycache__/`, `.venv/`
- [ ] `infra/scoutmatch_agent_extension/.local/` (state, validation JSON)
- [ ] `fix_agent_model.py`, `repair_agent_runtime.py` (untracked repair helpers)
- [ ] Generated submission ZIP file itself

## Screenshots

### Baseline v14 (captured)

- [x] `submission_evidence/final_v14/` — 11 PNGs (see `submission_evidence/README.md`)

### Dynamic extension (planned / missing)

- [ ] Agent KB association ENABLED
- [ ] Four user-facing Tools only
- [ ] Sporting-director chat, confirmation, DynamoDB, SNS, inline SVG lineup
- [ ] See `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md`

## Verification

- [ ] `python -m pytest tests/test_scoutmatch.py tests/test_bedrock_agent_advisor.py infra/scoutmatch_agent_extension/tests -q`
- [ ] Production: http://3.239.47.249/api/health and `/api/status` → `ready: true`, `rag_backend: aws_kb`
- [ ] `docs/COURSE_REQUIREMENTS_COMPLIANCE_MATRIX.md` reviewed

## Cleanup (deferred)

Do **not** delete AWS resources, production Docker, or KB content until:

1. Screenshots captured  
2. Final ZIP reviewed  
3. Live demo completed or evidence stored  
4. User explicitly approves (`docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md`)

## Presentation

- [ ] Build PPTX from `docs/SCOUTMATCH_PRESENTATION_CONTENT.md` (not in repo yet)
- [ ] Rehearse `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md`
