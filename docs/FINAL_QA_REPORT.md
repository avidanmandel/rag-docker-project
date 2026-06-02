# ScoutMatch AI — Final QA Report

**Audit date:** 2026-06-02 (UTC)  
**Branch:** `feature/session-scoped-documents`  
**Release commit:** `a587cf4e64a7bf17094271071ca72a941c475427`  
**Production image:** `scoutmatch-ai:session-docs-v9` (`fe16ae277316`)

## Phase 1 — Release state

| Check | Result |
|-------|--------|
| Local HEAD | `a587cf4` |
| Remote HEAD | `a587cf4` |
| EC2 release folder HEAD | `a587cf4` |
| Production container | `scoutmatch-ai` running |
| Source checksum vs container | **All match** (5/5 files) |
| Public endpoints | HTTP 200 |
| `rag_backend` / `engine_class` / `ready` | `aws_kb` / `AWSKnowledgeBaseEngine` / `true` |

## Phase 4 — Deploy script reliability

**Fixed:** `deploy_session_docs_v9.sh` now uses validation runner exit code (`$?`) instead of stale `PIPESTATUS` in the deploy shell.  
**Fixed:** `run_full_live_validation_v8.sh` captures Python exit via `PIPESTATUS[0]` inside the runner, writes full log to `$LOG_FILE`, prints validation summary.  
**Added:** `.gitattributes` (`*.sh text eol=lf`) to prevent CRLF bash failures on EC2.  
**App deployment:** Not required (docs/scripts only).

## Phase 5 — Strict loopback candidate validation

**Image:** existing `scoutmatch-ai:session-docs-v9`  
**Result:** **FAIL** — 3 blockers (all Amit Levy missing from aggregate answers)

| Test | Result |
|------|--------|
| Endpoints / status | PASS |
| English single-player (Or David) | PASS |
| Hebrew single-player | PASS |
| English relocation (6 players) | **FAIL** — missing Amit Levy |
| Hebrew relocation (6 players) | **FAIL** — missing Amit Levy |
| English salary total | PASS — 471,000 EUR |
| Hebrew salary total | PASS — 471,000 EUR |
| Defender comparison | **FAIL** — missing Amit Levy |
| Immediate availability (6 players) | PASS |
| Refusals (Titanic, Trump, Hebrew OOD) | PASS |
| Prompt injection | PASS |
| Delete one document | PASS |
| Stale-answer metadata | PASS |
| Clear documents | PASS |
| Session A/B isolation | PASS |
| Delete during sync | PASS |
| Restart persistence | **Not completed** (runner exited on SESSION_B 404) |
| Reconcile dry-run | **Not completed** in this run |
| Cleanup | Manual — candidate removed post-audit |

## Phase 6 — Unit tests

```
python -m pytest tests/test_scoutmatch.py -q --tb=no
238 passed, 4 warnings, 0 failures, ~15s
```

## Phase 7 — Public smoke

All endpoints HTTP 200. Production v9 active. No candidate containers remaining after manual cleanup.

## Phase 8 — Package audit

**Required files:** present (`app.py`, `requirements.txt`, `Dockerfile`, `README.md`, `templates/`, `static/`, core modules, `sample_scout_data/`, `docs/`, `tests/`).

**Secrets tracked in git:** none (`.env`, PEM, keys, `chat.db`, `runtime/` gitignored).

**Untracked classification:**

| Class | Examples |
|-------|----------|
| A — source/docs | `docs/*.md`, `scripts/run_strict_release_audit_v9.sh`, `scripts/ec2_checksum_check.sh`, `sample_scout_data/player_cvs/amit_levy_data.csv` |
| B — local logs | `artifacts/logs/*.log` (gitignored) |
| C — temp audit scripts | `scripts/audit_*.py`, `scripts/deploy_session_docs_v3-v7.sh`, `scripts/validate_*.py` |
| D — preview files | `home-preview-*.png`, `static/images/*-home.png` |
| E — sensitive local | `.env` (gitignored, present locally) |

## Verdict

| Criterion | Status |
|-----------|--------|
| **release_ready** | **no** — strict candidate audit has 3 blockers (Amit Levy absent from relocation/defender aggregates) |
| **submission_package_ready** | **yes** — docs complete, unit tests pass, package auditable; document known aggregate gap |
| **Production cutover** | Not performed (v9 already running; no new image) |

### Blockers

1. English relocation answer omits **Amit Levy** (5/6 names).
2. Hebrew relocation answer omits **Amit Levy**.
3. Defender comparison omits **Amit Levy**.

### Non-blocking issues

- Strict audit runner persistence/reconcile phases aborted on `set -e` after SESSION_B 404 (script robustness, not product regression).
- Shell scripts require LF line endings on EC2 (mitigated via `.gitattributes` + `sed` on deploy).
- 4 pytest deprecation warnings (third-party / Python 3.14).

### Recommended next action

Apply the **smallest runtime fix**: ensure `defender_amit_levy.csv` upload facts (`parsed_player_name`, `parsed_relocation`) flow into `session_player_facts` and deterministic aggregate builders (`build_relocation_list_answer`, defender comparison) so Amit Levy is always listed when CSV facts mark relocation YES. Re-run `scripts/run_strict_release_audit_v9.sh` on EC2; cut over only if BLOCKERS=0.

## Log artifacts (local only, not committed)

- `artifacts/logs/final_unit_tests.log`
- `artifacts/logs/final_candidate_validation.log`
- `artifacts/logs/final_public_smoke.log`
- `artifacts/logs/final_reconciliation.log`
