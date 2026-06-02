# ScoutMatch AI — RAG Data Lifecycle

This document describes the **actual** production data flow for session-scoped documents in AWS Knowledge Base mode (`RAG_BACKEND=aws_kb`).

## Key concepts

| Layer | What it stores | Purpose |
|-------|----------------|---------|
| S3 source object | Raw file bytes (TXT, PDF, DOCX, CSV, …) | Authoritative document content |
| S3 `.metadata.json` sidecar | `session_id`, `display_name`, `category` | Bedrock retrieval filter |
| SQLite `session_documents` | Registry of active uploads per conversation | UI list, safe delete targets |
| SQLite `sessions.document_revision` | Monotonic counter per conversation | Detect document-set changes |
| SQLite `sessions.synced_revision` | Last revision indexed by Bedrock | Gate retrieval until sync complete |
| Bedrock vector index | Embeddings/chunks derived from S3 | Semantic retrieval (not the same as S3 files) |

**Important:** Deleting an S3 object alone does not instantly remove vectors. A Bedrock ingestion job must complete before retrieval reflects the change. Until `synced_revision == document_revision`, the API blocks new grounded answers and returns a friendly updating message.

Historical assistant messages remain visible but are marked stale in the UI when `document_revision_at_answer < document_revision`.

---

## Session isolation

Each conversation has a unique `session_id`. S3 keys, metadata sidecars, SQLite `session_documents` rows, and Bedrock retrieval filters all include that ID. Session A cannot list, retrieve, or answer from Session B uploads. Cross-session leakage is blocked at the storage registry and retrieval filter layers.

---

## Stale historical answers

When the document set changes (upload, delete one, clear):

1. `document_revision` increments.
2. New questions wait for sync (`synced_revision == document_revision`) before grounded retrieval.
3. Existing assistant messages keep their original text but store `document_revision_at_answer`.
4. If `document_revision_at_answer < document_revision`, the UI shows a stale badge — the answer may not reflect the current documents.

Deleting one document removes its S3 source and sidecar; remaining documents stay searchable. Clearing documents removes all sources but retains the conversation messages.

---

## Upload flow

Each successful upload increments `document_revision` and triggers Bedrock sync. `synced_revision` advances only after ingestion succeeds.

```
Browser file input
  → POST /api/sessions/<session_id>/documents/upload
  → validate_upload() (extension, size, path traversal)
  → duplicate check (content SHA-256, same-name replace)
  → upload_session_document()
      → S3: scoutmatch/knowledge-base/sessions/<session_id>/<filename>
      → S3: <key>.metadata.json
  → database.add_session_document() (+ content_hash)
  → bump_document_revision() → sync_state=SYNCING
  → sync_knowledge_base() (bounded retry on ConflictException)
  → mark_sync_success() → synced_revision=document_revision, READY
  → JSON 201 + ingestion_job_id
```

Frontend shows upload progress, polls ingestion status, disables duplicate actions during sync.

---

## Delete one document

```
Browser document trash
  → DELETE /api/sessions/<session_id>/documents/<id>
  → validate session + DB ownership
  → delete_recorded_session_objects() (strict session prefix + sidecar)
  → database.delete_session_document()
  → bump_document_revision() + sync_knowledge_base()
  → mark_sync_success() or mark_sync_error()
```

Historical chat answers referencing the deleted document remain but show a stale badge after revision increments.

---

## Clear documents

```
Browser "Clear documents"
  → POST /api/sessions/<session_id>/documents/clear
  → list DB rows for session only
  → delete S3 sources + sidecars (prefix guard)
  → clear session_documents rows
  → bump revision + sync
  → session and messages retained
```

New questions refuse or return updating message until sync completes; old answers marked stale.

---

## Delete conversation

```
Browser header trash
  → DELETE /api/sessions/<session_id>  { delete_documents: true }
  → delete S3 sources + sidecars for registered docs
  → clear session_documents rows
  → delete messages + session row (always, even if sync pending)
  → best-effort Bedrock sync (does not block deletion)
  → UI refreshes sidebar, selects next session or creates new one
```

---

## Retrieval / answer flow

```
POST /api/sessions/<session_id>/messages
  → if not is_retrieval_ready(): friendly syncing refusal, zero sources
  → engine.answer()
      → domain gate (out-of-domain → refusal, zero sources)
      → Bedrock retrieve() filtered by metadata session_id
      → football relevance filter (excludes titanic.csv-style noise)
      → aggregate or diverse context selection
      → Bedrock Converse generation
      → sanitize_bedrock_answer + quality validation
  → _finalize_assistant_result() clears sources on refused
  → persist message with document_revision_at_answer
```

Refused answers never include Main source or Retrieved evidence cards.

---

## Sync states

| State | Meaning |
|-------|---------|
| `READY` | `synced_revision == document_revision`; retrieval allowed |
| `SYNCING` | Document set changed; ingestion in progress |
| `ERROR` | Last sync failed; retrieval blocked until next successful sync |

---

## Reconciliation

Run read-only audit:

```bash
python scripts/reconcile_session_documents.py --dry-run
```

Reports DB/S3/sidecar mismatches without deleting production data.
