# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Branch** | `feature/session-scoped-documents` |
| **Release commit** | `1978bb3` |
| **Production image** | `scoutmatch-ai:baseline-club-v14` |
| **Rollback image** | `scoutmatch-ai:baseline-club-v13` |
| **Public URL** | http://3.239.47.249/ |
| **Production container** | `scoutmatch-ai` |
| **Baseline set (production)** | `production` (10 managed documents) |
| **Last QA** | 2026-06-03 (UTC) |

## v14 lifecycle and document-delete fixes

| Check | Result |
|-------|--------|
| Unit tests (`test_scoutmatch` + `test_baseline_club_knowledge`) | **273 passed** |
| Targeted preflight (Eyal Mor delete, clear docs, partial budget combo) | **BLOCKERS 0** |
| Public post-cutover verification | **HTTP 200**, `ready=true`, `baseline_ready=true` |
| Production `baseline_ready` | **true** |
| Bedrock sync (scoutmatch-player-documents) | **COMPLETE**, 0 failed, 0 warnings |

## Knowledge scopes

- **Baseline (read-only):** `scoutmatch/knowledge-base/baseline/production/`
- **Session candidates:** `scoutmatch/knowledge-base/sessions/<session_id>/`

## Notes

- v14 fixes stale facts after single-document delete, clear-documents listing, and partial budget combo fall-through.
- Hebrew synonym routing remains deterministic for baseline-only and registry-backed candidate intents.
- Final submission screenshots live in `submission_evidence/final_v14/`.
- AWS cleanup `--apply` not executed. EC2 and Bedrock KB remain active pending post-submission teardown approval.
