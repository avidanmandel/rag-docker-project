# ScoutMatch AI — Final QA Report

**Audit date:** 2026-06-03 (UTC)  
**Branch:** `feature/session-scoped-documents`  
**Release commit:** `1978bb30eb340c77262784d2781516862148b2e4`  
**Production image:** `scoutmatch-ai:baseline-club-v14`  
**Rollback image:** `scoutmatch-ai:baseline-club-v13`  
**Public URL:** http://3.239.47.249/

## v14 fix summary

- **Document delete lifecycle** — Early revision bump on delete/clear prevents stale registry answers while KB sync is in flight.
- **Retrieved chunk filtering** — Session answers filter KB chunks to active `session_document_names` only.
- **Named-player salary/relocation** — Named-player questions use session-scope refusal when documents are removed.
- **Partial budget combo** — After deleting one of two budget players, combo questions refuse instead of falling through to stale KB chunks.
- **Clear-documents API** — Listing no longer counts baseline files in session document responses.

## Strict validation (v14 candidate + public)

**Result:** **PASS — BLOCKERS 0**

| Test area | Result |
|-----------|--------|
| Eyal Mor CSV upload → salary/relocation → delete → refusal | PASS |
| Format delete (PDF/DOCX/TXT/CSV) lifecycle | PASS |
| Clear documents (two files → refusal) | PASS |
| Delete one of two budget players → combo refusal | PASS |
| Session isolation / delete conversation | PASS |
| Public `/`, `/api/health`, `/api/status` | PASS |
| Bedrock ingestion after targeted warning cleanup | COMPLETE, 0 failed, 0 warnings |

## Unit tests

```
python -m pytest tests/test_scoutmatch.py tests/test_baseline_club_knowledge.py -q --tb=no
273 passed
```

## Production cutover

- Cutover from `baseline-club-v13` → `baseline-club-v14` after candidate BLOCKERS 0.
- Production DB backed up under `/home/ubuntu/scoutmatch-ai-runtime/rollback/` before cutover.
- Container `scoutmatch-ai` on image `scoutmatch-ai:baseline-club-v14`, port 80→5000, restart unless-stopped.

## Verdict

| Criterion | Status |
|-----------|--------|
| **release_ready** | **yes** |
| **baseline_club_knowledge** | **enabled** |
| **submission_evidence** | **11 PNGs in `submission_evidence/final_v14/`** |

## Artifacts

- Deploy script: `scripts/deploy_baseline_club_v14.sh`
- Targeted preflight: `scripts/final_targeted_preflight.py`
- Submission screenshots: `submission_evidence/final_v14/`
- AWS cleanup dry-run only (`scripts/aws_cleanup_dry_run.sh`) — no deletions applied
