# ScoutMatch AI — Submission Checklist

Use this checklist before submitting the lesson project ZIP.

## Required source files

- [ ] `app.py`
- [ ] `requirements.txt`
- [ ] `Dockerfile`
- [ ] `README.md`
- [ ] `templates/` (UI)
- [ ] `static/` (CSS, JS, images)
- [ ] `aws_kb_engine.py`
- [ ] `aws_storage_service.py`
- [ ] `database.py`
- [ ] `requirement_verification.py`
- [ ] `sample_scout_data/` (demo player CVs and reports)
- [ ] `docs/` (project state, lifecycle, runbook, QA report, limitations, this checklist)
- [ ] `tests/test_scoutmatch.py`

## Screenshots (for report / demo)

Capture from production or candidate UI:

- [ ] Home dashboard
- [ ] Upload panel with documents listed
- [ ] Grounded English answer with source cards
- [ ] Grounded Hebrew answer
- [ ] Refusal (out-of-domain) with no sources
- [ ] Stale-answer badge after document delete
- [ ] Clear documents / session isolation (optional)

Store screenshots outside `artifacts/logs/` or exclude from ZIP if not required by rubric.

## README

- [ ] Architecture section matches AWS KB production path
- [ ] Environment variables documented (no secret values)
- [ ] Local vs production mode explained
- [ ] Link or reference to `docs/DEPLOYMENT_RUNBOOK.md`

## Clean ZIP

Before zipping:

- [ ] **Exclude** `.env`, `*.pem`, `*.key`, `chat.db`, `runtime/`, `.aws/`
- [ ] **Exclude** `artifacts/logs/`, `*.log`
- [ ] **Exclude** `__pycache__/`, `.venv/`, `.pytest_cache/`
- [ ] **Exclude** local preview PNGs unless required (`home-preview-*.png`)
- [ ] **Exclude** one-off audit/deploy scripts (`scripts/deploy_session_docs_v3.sh` … `v7`, `scripts/audit_*.py`) unless instructor requires full history
- [ ] **Include** `docs/FINAL_QA_REPORT.md` and `docs/PROJECT_STATE.md`

Suggested ZIP root: project folder name `Avidan_RAG_Docker_Project` with no nested duplicate folders.

## AWS cleanup after screenshots / demo

After capturing demo evidence:

- [ ] Delete disposable test sessions via UI or API (`delete_documents: true`)
- [ ] Run `python scripts/reconcile_session_documents.py --dry-run` on EC2 — expect no orphan keys for production sessions
- [ ] Confirm no leftover keys under `scoutmatch/knowledge-base/sessions/<test-session-id>/`
- [ ] Remove any loopback candidate containers and temp runtime dirs
- [ ] Do **not** delete production runtime `chat.db` or unrelated AWS resources

## Pre-submit verification

- [ ] `python -m pytest tests/test_scoutmatch.py -q` passes locally
- [ ] Production URL responds HTTP 200 on `/`, `/api/health`, `/api/status`
- [ ] `docs/FINAL_QA_REPORT.md` reflects latest strict candidate audit
- [ ] Git branch `feature/session-scoped-documents` pushed; release commit documented in `docs/PROJECT_STATE.md`
