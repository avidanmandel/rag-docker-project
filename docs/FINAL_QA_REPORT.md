# ScoutMatch AI — Final QA Report

**Audit date:** 2026-06-02 (UTC)  
**Branch:** `feature/session-scoped-documents`  
**Release commit:** `3f3d4b331d7d4672222eafe8f5a9d70a6f0c9365`  
**Production image:** `scoutmatch-ai:session-docs-v10`

## v10 fix summary

- Deterministic aggregates use upload-time `session_player_facts` (SQLite), not chunk extraction alone.
- `parsed_position` stored at upload for CSV/PDF/DOCX/TXT.
- Audit runner reads session IDs from `${LOG_FILE}`; persistence phase uses tolerant HTTP checks.
- Cleanup phase uses `timeout 45` on S3 listing to avoid hang.

## Strict loopback candidate (v10)

**Result:** **PASS — BLOCKERS 0**

| Test | Result |
|------|--------|
| English relocation (6 players incl. Amit Levy) | PASS |
| Hebrew relocation (6 players incl. Amit Levy) | PASS |
| Defender comparison (Amit Levy, Luca Romano, Noam David) | PASS |
| Salary total 471,000 EUR | PASS |
| Immediate availability (6 players) | PASS |
| Refusals / injection / delete / clear / isolation | PASS |
| Persistence restart + recreate | PASS |
| Reconcile dry-run | PASS (`complete: 1`) |

## Unit tests

```
python -m pytest tests/test_scoutmatch.py -q --tb=no
240 passed, 4 warnings, 0 failures, ~18s
```

## Fixture validation

```
python scripts/validate_release_fixtures.py
BLOCKERS 0 (TXT, CSV, PDF, DOCX)
```

## Production cutover

- Cutover from `session-docs-v9` → `session-docs-v10` after duplicate strict validation BLOCKERS 0.
- Public endpoints HTTP 200; `ready=true`.

## Verdict

| Criterion | Status |
|-----------|--------|
| **release_ready** | **yes** |
| **submission_package_ready** | **yes** |

## Artifacts

- Submission ZIP: `dist/Avidan_RAG_Docker_Project-submission.zip` (local)
- AWS cleanup dry-run: `scripts/aws_cleanup_dry_run.sh` (no deletions)
