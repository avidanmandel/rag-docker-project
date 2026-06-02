# ScoutMatch AI — Deployment Runbook

Production host: `ubuntu@3.239.47.249`  
Release checkout: `/home/ubuntu/scoutmatch-ai-session-docs-release`  
Runtime data: `/home/ubuntu/scoutmatch-ai-runtime` → `/app/runtime`

## Prerequisites

- SSH access with PEM key (never commit the key).
- `.env` on EC2 at release folder root (never print or commit).
- Docker available on EC2 (`sudo docker`).
- Branch `feature/session-scoped-documents` pushed to origin.

## Safe EC2-side build

```bash
cd /home/ubuntu/scoutmatch-ai-session-docs-release
git fetch origin feature/session-scoped-documents
git checkout feature/session-scoped-documents
git pull --ff-only origin feature/session-scoped-documents
sudo docker build -t scoutmatch-ai:session-docs-v9 .
```

Build on EC2 only. Do not use local Docker Desktop for production images.

## DB backup (before cutover)

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /home/ubuntu/scoutmatch-ai-runtime/rollback
sudo cp /home/ubuntu/scoutmatch-ai-runtime/chat.db \
  /home/ubuntu/scoutmatch-ai-runtime/rollback/chat.db.${TS}.bak
sudo chown ubuntu:ubuntu /home/ubuntu/scoutmatch-ai-runtime/rollback/chat.db.${TS}.bak
```

## Candidate container (loopback only)

Use an isolated runtime directory and bind loopback port 5001:

```bash
export IMAGE_TAG=scoutmatch-ai:session-docs-v9
export CANDIDATE=scoutmatch-ai-v9-release-audit-candidate
export RUNTIME=/home/ubuntu/scoutmatch-ai-v9-release-audit-runtime
export LOG_FILE=/tmp/strict_release_audit.log
export STRICT_AUDIT=1
bash scripts/run_full_live_validation_v8.sh
```

Or the release-audit wrapper:

```bash
bash scripts/run_strict_release_audit_v9.sh
```

Validation writes a full log to `$LOG_FILE`. The script exits non-zero on Python failures or `BLOCKERS > 0`.

## Endpoint checks (candidate)

After candidate health is up:

```bash
curl -fsS http://127.0.0.1:5001/api/health
curl -fsS http://127.0.0.1:5001/api/status
```

Confirm `rag_backend=aws_kb`, `engine_class=AWSKnowledgeBaseEngine`, `ready=true`.

## Cutover (production port 80)

Only after candidate validation passes:

```bash
bash scripts/deploy_session_docs_v9.sh
```

The deploy script:

1. Backs up `chat.db`
2. Pulls release branch
3. Builds image tag (if rebuilding)
4. Runs full candidate validation — **stops on non-zero exit or BLOCKERS**
5. Replaces `scoutmatch-ai` container with same runtime mount and `.env`

Post-cutover smoke on EC2:

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
curl -fsS http://127.0.0.1/api/status
```

## Rollback

If cutover fails or regressions appear:

```bash
sudo docker rm -f scoutmatch-ai
sudo docker run -d \
  --name scoutmatch-ai \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file /home/ubuntu/scoutmatch-ai-session-docs-release/.env \
  -v /home/ubuntu/scoutmatch-ai-runtime:/app/runtime \
  -e DATABASE_PATH=/app/runtime/chat.db \
  scoutmatch-ai:session-docs-v8
```

Restore DB from rollback backup if needed:

```bash
sudo cp /home/ubuntu/scoutmatch-ai-runtime/rollback/chat.db.TIMESTAMP.bak \
  /home/ubuntu/scoutmatch-ai-runtime/chat.db
sudo chown ubuntu:ubuntu /home/ubuntu/scoutmatch-ai-runtime/chat.db
sudo docker restart scoutmatch-ai
```

## Reconciliation (read-only)

```bash
sudo docker exec scoutmatch-ai python scripts/reconcile_session_documents.py --dry-run
```

## Cleanup

After candidate validation:

- Delete disposable sessions via API (`DELETE /api/sessions/<id>` with `delete_documents: true`).
- Confirm zero leftover S3 keys under session prefixes.
- Remove candidate container and runtime directory:

```bash
sudo docker rm -f scoutmatch-ai-v9-release-audit-candidate
rm -rf /home/ubuntu/scoutmatch-ai-v9-release-audit-runtime
```

## Deploy script reliability

`deploy_session_docs_v9.sh` checks the **exit code** of the validation runner and greps `BLOCKERS` from the log file. It does not rely on `PIPESTATUS` in the deploy shell after a subshell returns.

Shell scripts must use LF line endings (see `.gitattributes`).
