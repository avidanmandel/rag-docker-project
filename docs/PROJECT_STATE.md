# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Branch** | `feature/session-scoped-documents` |
| **Release commit** | `533726c` |
| **Production image** | `scoutmatch-ai:baseline-club-v13` |
| **Rollback image** | `scoutmatch-ai:baseline-club-v12` |
| **Public URL** | http://3.239.47.249/ |
| **Baseline set (production)** | `production` (10 managed documents) |
| **Last QA** | 2026-06-02 (UTC) |

## v13 Hebrew business-intent completion

| Check | Result |
|-------|--------|
| Unit tests (`test_scoutmatch` + `test_baseline_club_knowledge`) | **269 passed** |
| Hebrew business gate (loopback candidate) | **BLOCKERS 0** |
| Baseline business gate (loopback candidate) | **BLOCKERS 0** |
| Public Hebrew verification (post-cutover) | **BLOCKERS 0** |
| Production `baseline_ready` | **true** |

## Knowledge scopes

- **Baseline (read-only):** `scoutmatch/knowledge-base/baseline/production/`
- **Session candidates:** `scoutmatch/knowledge-base/sessions/<session_id>/`

## Notes

- Hebrew synonym routing is deterministic for baseline-only and registry-backed candidate intents.
- **מגן ימני** (Right Back) is distinct from **בלם ימני** (right-sided centre back); the latter returns insufficient-information, not a Right Back mapping.
- Screenshot PNG files unchanged (no screenshot automation).
- AWS cleanup `--apply` not executed.
- EC2 and Bedrock KB remain active.
