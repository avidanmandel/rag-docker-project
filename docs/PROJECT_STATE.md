# ScoutMatch AI — Project State

| Field | Value |
|-------|-------|
| **Project name** | ScoutMatch AI |
| **Branch** | `feature/session-scoped-documents` |
| **Release commit** | `a587cf4e64a7bf17094271071ca72a941c475427` |
| **Production image** | `scoutmatch-ai:session-docs-v9` |
| **Image ID** | `fe16ae277316` |
| **Container name** | `scoutmatch-ai` |
| **Public URL** | http://3.239.47.249/ |
| **Runtime mount** | `/home/ubuntu/scoutmatch-ai-runtime:/app/runtime` |
| **DB path** | `DATABASE_PATH=/app/runtime/chat.db` |
| **Rollback image** | `scoutmatch-ai:session-docs-v8` |
| **Last QA timestamp** | 2026-06-02T10:40Z (UTC) |

## Release verification (2026-06-02)

| Check | Result |
|-------|--------|
| Local HEAD | `a587cf4` |
| Remote HEAD | `a587cf4` (matches local) |
| EC2 release folder HEAD | `a587cf4` |
| Container state | running |
| Source checksum vs container | **match** (`app.py`, `aws_kb_engine.py`, `database.py`, `requirement_verification.py`, `aws_storage_service.py`) |
| `rag_backend` | `aws_kb` |
| `engine_class` | `AWSKnowledgeBaseEngine` |
| `ready` | `true` |

## Notes

- Production v9 remains active during loopback candidate audits.
- Candidate validation uses disposable sessions and synthetic documents only.
- Do not commit `.env`, PEM keys, `chat.db`, or raw logs under `artifacts/logs/`.
