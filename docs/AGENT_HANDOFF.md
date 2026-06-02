# Agent Handoff — ScoutMatch AI

Last updated: 2026-06-02

## Current state

| Item | Value |
|------|-------|
| Branch | `feature/session-scoped-documents` |
| Release commit | `533726c` |
| Production image | `scoutmatch-ai:baseline-club-v13` |
| Rollback | `scoutmatch-ai:baseline-club-v12` |
| Hebrew gate | **BLOCKERS 0** (loopback + public) |
| Baseline gate | **BLOCKERS 0** |
| EC2 | `ubuntu@3.239.47.249` |
| Checkout | `/home/ubuntu/scoutmatch-ai-session-docs-release` |

## v13 highlights (Hebrew business-intent)

- Reusable Hebrew intent classification (`classify_baseline_question_intent`) for baseline-only questions.
- Early deterministic routing in `aws_kb_engine.answer()` before Bedrock retrieval (baseline + registry).
- Hebrew domain allow-list for structured recruitment intents.
- **מגן ימני** (Right Back) vs **בלם ימני** (centre back) semantic distinction.
- Focused gate: `bash scripts/run_hebrew_business_gate.sh`

## Validation

```bash
bash scripts/run_hebrew_business_gate.sh      # Hebrew canonical + variants
bash scripts/run_baseline_business_gate.sh      # full baseline + demo gate
python -m pytest tests/test_baseline_club_knowledge.py tests/test_scoutmatch.py -q
```

## Rollback

```bash
sudo docker stop scoutmatch-ai && sudo docker rm scoutmatch-ai
sudo docker run -d --name scoutmatch-ai -p 0.0.0.0:80:5000 --restart unless-stopped \
  --env-file /home/ubuntu/scoutmatch-ai-session-docs-release/.env \
  -v /home/ubuntu/scoutmatch-ai-runtime:/app/runtime \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e BASELINE_KNOWLEDGE_ENABLED=true -e AWS_BASELINE_SET_ID=production \
  scoutmatch-ai:baseline-club-v12
```

## Do not

- Run AWS cleanup `--apply` without explicit approval.
- Modify screenshot PNG files or run screenshot automation.
- Delete production user sessions/documents during verification.
