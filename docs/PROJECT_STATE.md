# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Project name** | ScoutMatch AI |
| **Branch** | `feature/session-scoped-documents` |
| **Release commit** | `bb8598b` (`3f3d4b3` app fix + `bb8598b` deploy scripts) |
| **Production image** | `scoutmatch-ai:session-docs-v10` |
| **Image ID** | `801e957a392b` |
| **Container name** | `scoutmatch-ai` |
| **Public URL** | http://3.239.47.249/ |
| **Runtime mount** | `/home/ubuntu/scoutmatch-ai-runtime:/app/runtime` |
| **DB path** | `DATABASE_PATH=/app/runtime/chat.db` |
| **Rollback image** | `scoutmatch-ai:session-docs-v9` |
| **Last QA timestamp** | 2026-06-02 (UTC) |

## v10 changes

- Upload-time `session_player_facts` used for all deterministic aggregates.
- `parsed_position` stored at upload for CSV/PDF/DOCX/TXT.
- Audit runner: `${LOG_FILE}` session IDs, tolerant persistence checks, S3 cleanup timeout.

## Release verification (2026-06-02)

| Check | Result |
|-------|--------|
| Local / remote / EC2 HEAD | `bb8598b` / `bb8598b` / `3f3d4b3+` |
| Strict candidate audit | **BLOCKERS 0** |
| Source checksum vs container | **match** (5/5 files) |
| Production | `session-docs-v10` active |
| `rag_backend` / `engine_class` / `ready` | `aws_kb` / `AWSKnowledgeBaseEngine` / `true` |

## Notes

- Cutover performed after strict validation BLOCKERS 0.
- Submission ZIP: `dist/Avidan_RAG_Docker_Project-submission.zip`
- AWS cleanup: dry-run only via `scripts/aws_cleanup_dry_run.sh`
