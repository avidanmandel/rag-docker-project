#!/usr/bin/env bash
# Restart isolated V2 staging container on EC2 (127.0.0.1:5002 only).
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-session-docs-release}"
RUNTIME_DIR="${RUNTIME_DIR:-/home/ubuntu/scoutmatch-ai-v2-staging-runtime}"
IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:v2-staging-candidate}"
CONTAINER="${CONTAINER:-scoutmatch-ai-v2-staging-candidate}"
BRANCH="${BRANCH:-feature/scoutmatch-business-workflow-v2}"
STAGING_ALIAS_ID="${STAGING_ALIAS_ID:-T6N3TXAMCJ}"

cd "${APP_DIR}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}" || true

mkdir -p "${RUNTIME_DIR}"
sudo docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true

sudo docker build -t "${IMAGE_TAG}" .

sudo docker run -d \
  --name "${CONTAINER}" \
  -p 127.0.0.1:5002:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e SCOUTMATCH_AGENT_EXTENSION_ENABLED=true \
  -e SCOUTMATCH_AGENT_ID=3YMQVGTYSG \
  -e SCOUTMATCH_AGENT_ALIAS_ID="${STAGING_ALIAS_ID}" \
  -e SCOUTMATCH_AGENT_STAGING_ALIAS_ID="${STAGING_ALIAS_ID}" \
  -e SCOUTMATCH_BUSINESS_WORKFLOW_V2_ENABLED=true \
  -e SCOUTMATCH_EMAIL_MODE=disabled \
  -e SCOUTMATCH_CALENDAR_MODE=ics_fallback \
  -e SCOUTMATCH_SCOUTING_REMINDER_MODE=disabled \
  -e SCOUTMATCH_DEMO_REPLAY_ENABLED=true \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  -e SCOUTMATCH_LINEUP_BUCKET="${SCOUTMATCH_LINEUP_BUCKET:-oz-bucket-user5}" \
  -e SCOUTMATCH_FOOTBALL_OPS_TABLE="${SCOUTMATCH_FOOTBALL_OPS_TABLE:-ScoutMatchFootballOperationsAvidan}" \
  -e SCOUTMATCH_FOOTBALL_OPS_HASH_KEY="${SCOUTMATCH_FOOTBALL_OPS_HASH_KEY:-entity_key}" \
  "${IMAGE_TAG}"

for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:5002/api/health >/dev/null 2>&1 && break
  sleep 2
done

echo "=== staging status ==="
curl -fsS http://127.0.0.1:5002/api/status
echo
