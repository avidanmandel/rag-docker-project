# ScoutMatch AI — Deployment Runbook

**Active release:** `scoutmatch-ai:baseline-club-v14`  
**Public URL:** http://3.239.47.249/  
**Production container:** `scoutmatch-ai`

This runbook describes the current EC2 production layout for lecturer review. It does not include historical deploy scripts.

---

## Production layout

| Item | Value |
|------|-------|
| Host | `ubuntu@3.239.47.249` |
| Release checkout | `/home/ubuntu/scoutmatch-ai-session-docs-release` |
| Runtime mount | `/home/ubuntu/scoutmatch-ai-runtime:/app/runtime` |
| Container name | `scoutmatch-ai` |
| Image | `scoutmatch-ai:baseline-club-v14` |
| Rollback image | `scoutmatch-ai:baseline-club-v13` |
| Port mapping | `80:5000` (host → container) |
| Restart policy | `unless-stopped` |
| Database path | `/app/runtime/chat.db` (inside container) |

---

## Environment configuration

- Copy `.env.ec2.example` to `.env` on the EC2 host (**never commit `.env`**).
- Fill in Bedrock and S3 identifiers only — **do not** embed AWS access keys in the image.
- Production uses the **EC2 instance IAM role** for boto3 authentication.
- Baseline club mode (production):

  ```
  BASELINE_KNOWLEDGE_ENABLED=true
  AWS_BASELINE_SET_ID=production
  ```

- Secrets, PEM keys, and tokens must stay outside the Docker image.

---

## Build and run (EC2)

Build on EC2 only:

```bash
cd /home/ubuntu/scoutmatch-ai-session-docs-release
sudo docker build -t scoutmatch-ai:baseline-club-v14 .
```

Run production container:

```bash
sudo docker run -d \
  --name scoutmatch-ai \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file /home/ubuntu/scoutmatch-ai-session-docs-release/.env \
  -v /home/ubuntu/scoutmatch-ai-runtime:/app/runtime \
  -e DATABASE_PATH=/app/runtime/chat.db \
  scoutmatch-ai:baseline-club-v14
```

Verify running container:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
sudo docker inspect -f 'restart_policy={{.HostConfig.RestartPolicy.Name}}' scoutmatch-ai
```

---

## Health checks

After deploy or cutover, confirm:

```bash
curl -fsS http://127.0.0.1/
curl -fsS http://127.0.0.1/api/health
curl -fsS http://127.0.0.1/api/status
```

Public endpoints:

- http://3.239.47.249/
- http://3.239.47.249/api/health
- http://3.239.47.249/api/status

Expected `/api/status` fields:

- `ready: true`
- `baseline_ready: true`
- `rag_backend: aws_kb`
- `engine_class: AWSKnowledgeBaseEngine`

---

## DB backup (before image rollback)

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /home/ubuntu/scoutmatch-ai-runtime/rollback
sudo cp /home/ubuntu/scoutmatch-ai-runtime/chat.db \
  /home/ubuntu/scoutmatch-ai-runtime/rollback/chat.db.${TS}.bak
sudo chown ubuntu:ubuntu /home/ubuntu/scoutmatch-ai-runtime/rollback/chat.db.${TS}.bak
```

---

## Rollback to v13

If v14 regressions appear after backup:

```bash
sudo docker rm -f scoutmatch-ai
sudo docker run -d \
  --name scoutmatch-ai \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file /home/ubuntu/scoutmatch-ai-session-docs-release/.env \
  -v /home/ubuntu/scoutmatch-ai-runtime:/app/runtime \
  -e DATABASE_PATH=/app/runtime/chat.db \
  scoutmatch-ai:baseline-club-v13
```

Restore DB from rollback backup only if required:

```bash
sudo cp /home/ubuntu/scoutmatch-ai-runtime/rollback/chat.db.TIMESTAMP.bak \
  /home/ubuntu/scoutmatch-ai-runtime/chat.db
sudo chown ubuntu:ubuntu /home/ubuntu/scoutmatch-ai-runtime/chat.db
sudo docker restart scoutmatch-ai
```

---

## Notes

- No AWS access keys belong inside the Docker image; use the EC2 IAM role.
- Shell scripts on EC2 must use LF line endings (see `.gitattributes`).
- Do not terminate EC2 or delete the Bedrock Knowledge Base without explicit post-submission approval.
