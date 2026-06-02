# ScoutMatch AI — Final QA Report

**Audit date:** 2026-06-02 (UTC)  
**Branch:** `feature/session-scoped-documents`  
**Production image:** `scoutmatch-ai:session-docs-v11`  
**Rollback image:** `scoutmatch-ai:session-docs-v10`

## v11 fix summary

- **Salary aggregate 471,000 EUR** — Quoted CSV values (`"58,000 EUR"`) now parse; Amit Levy salary included in registry totals.
- **CV + scouting report merge** — Two-pass registry: CVs seed facts; scouting reports enrich without erasing structured CV fields or creating duplicate players.
- **Deterministic filters** — Left foot, defender relocation (EN/HE), GK immediate + salary ceiling, cheapest right back (EN/HE) use upload-time registry facts.
- **Invalid document validation** — Corrupt PDF/DOCX, malformed CSV, empty files, exe, path traversal, oversize rejected with HTTP 400; no S3/DB/revision side effects.

## Business acceptance gate (v11 loopback)

**Result:** **PASS — BLOCKERS 0**  
**Log:** `/tmp/business_gate_v11_iter3.log` on EC2

| Mandatory test | Expected | Result |
|----------------|----------|--------|
| BA-AGG-salary | 471,000 EUR | PASS |
| BA-FLT-left-foot | Pedro Silva + Luca Romano | PASS |
| BA-FLT-defender-reloc | Amit Levy + Luca Romano only | PASS |
| BA-FLT-he-def | Amit Levy + Luca Romano (Hebrew) | PASS |
| BA-FLT-goalkeeper | Marco Silva only (≤70k immediate) | PASS |
| BA-FLT-cheapest-rb | Ron Ben Ari, 43,000 EUR | PASS |
| BA-FLT-he-rb | Ron Ben Ari, 43,000 EUR (Hebrew) | PASS |
| BA-INV corrupt/malformed | HTTP 4xx | PASS |
| Persistence restart + recreate | HTTP 200 | PASS |
| Reconcile dry-run | complete | PASS |
| Final disposable S3 keys | 0 | PASS |

## Unit tests

```
python -m pytest tests/test_scoutmatch.py -q --tb=no
250 passed, 4 warnings, 0 failures, ~8s
```

## Production cutover

- Cutover from `session-docs-v10` → `session-docs-v11` after business gate BLOCKERS 0.
- Production DB backed up under `/home/ubuntu/scoutmatch-ai-runtime/rollback/` before cutover.
- Public endpoints HTTP 200; `ready=true`.

## Verdict

| Criterion | Status |
|-----------|--------|
| **release_ready** | **yes** |
| **baseline_club_knowledge** | **not started** |

## Artifacts

- Business gate runner: `scripts/run_business_acceptance_gate.py` + `.sh`
- Fixtures: `tests/fixtures/business_acceptance/` (35 files)
- AWS cleanup dry-run: `scripts/aws_cleanup_dry_run.sh` (no deletions)
