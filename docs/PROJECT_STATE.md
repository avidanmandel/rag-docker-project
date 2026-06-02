# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Project name** | ScoutMatch AI |
| **Branch** | `feature/session-scoped-documents` |
| **Release commit** | v11 business-gate cutover (see git log) |
| **Production image** | `scoutmatch-ai:session-docs-v11` |
| **Rollback image** | `scoutmatch-ai:session-docs-v10` |
| **Container name** | `scoutmatch-ai` |
| **Public URL** | http://3.239.47.249/ |
| **Runtime mount** | `/home/ubuntu/scoutmatch-ai-runtime:/app/runtime` |
| **DB path** | `DATABASE_PATH=/app/runtime/chat.db` |
| **Last QA timestamp** | 2026-06-02 (UTC) |

## Business acceptance gate (v11)

| Check | Result |
|-------|--------|
| Static UI checks (12) | **PASS** |
| Format matrix (TXT/PDF/DOCX/CSV/BOM/Unicode/spaces) | **PASS** |
| Salary total 471,000 EUR | **PASS** |
| Left foot (Pedro Silva + Luca Romano) | **PASS** |
| Defender relocation EN/HE (Amit Levy + Luca Romano) | **PASS** |
| GK immediate ≤70k (Marco Silva only) | **PASS** |
| Cheapest right back EN/HE (Ron Ben Ari, 43,000 EUR) | **PASS** |
| Invalid document validation (4xx, no side effects) | **PASS** |
| Lifecycle / isolation / persistence / reconcile | **PASS** |
| v11 loopback gate blockers | **0** |
| Production cutover | **session-docs-v11** |

## v11 changes

- Deterministic structured filters: left foot, defender relocation, GK compound, cheapest right back (EN/HE).
- Upload-time registry merge: CV salary retained; scouting reports enrich only; unrelated fixtures excluded.
- Quoted CSV salary values parsed correctly (`"58,000 EUR"`).
- Invalid uploads rejected before S3/DB (corrupt PDF/DOCX, malformed CSV, empty, exe, traversal, oversize).

## Release verification

| Check | Result |
|-------|--------|
| Unit tests | **250 passed**, 4 warnings |
| Business gate EC2 | **BLOCKERS 0** (`/tmp/business_gate_v11_iter3.log`) |
| Source checksum vs container | verify after cutover |
| `rag_backend` / `engine_class` / `ready` | `aws_kb` / `AWSKnowledgeBaseEngine` / `true` |

## Notes

- Baseline club-knowledge feature **not started** (deferred).
- AWS cleanup: dry-run only via `scripts/aws_cleanup_dry_run.sh` (no `--apply`).
- Submission ZIP: `dist/Avidan_RAG_Docker_Project-submission.zip`
