# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Branch** | `feature/session-scoped-documents` |
| **Release commit** | `0a7be41` |
| **Production image** | `scoutmatch-ai:baseline-club-v12` |
| **Image ID** | `915ec8bc45c4` |
| **Rollback image** | `scoutmatch-ai:session-docs-v11` |
| **Public URL** | http://3.239.47.249/ |
| **Baseline set (production)** | `production` (10 managed documents) |
| **Last QA** | 2026-06-02 (UTC) |

## v12 baseline club knowledge

| Check | Result |
|-------|--------|
| Baseline business gate (loopback) | **BLOCKERS 0** (`/tmp/baseline_gate_v12_final.log`) |
| v11 business gate (prior release) | **BLOCKERS 0** |
| Unit tests | **262 passed** |
| Production `baseline_ready` | **true** |
| Runtime checksum vs checkout | **5/5 match** |

## Knowledge scopes

- **Baseline (read-only):** `scoutmatch/knowledge-base/baseline/production/`
- **Session candidates:** `scoutmatch/knowledge-base/sessions/<session_id>/`

## Notes

- Screenshot PNG files unchanged (manual capture deferred).
- AWS cleanup `--apply` not executed.
- EC2 and Bedrock KB remain active.
