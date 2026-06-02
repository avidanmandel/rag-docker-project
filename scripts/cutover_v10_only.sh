#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
RUNTIME_DIR="/home/ubuntu/scoutmatch-ai-runtime"
IMAGE_TAG="scoutmatch-ai:session-docs-v10"
PROD_CONTAINER="scoutmatch-ai"

sudo docker rm -f scoutmatch-ai-v10-full-validation-candidate scoutmatch-ai-v10-release-audit-candidate 2>/dev/null || true
rm -rf /home/ubuntu/scoutmatch-ai-v10-full-validation-runtime /home/ubuntu/scoutmatch-ai-v10-release-audit-runtime

PROD_IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}")
sudo docker rm -f "${PROD_CONTAINER}"
sudo docker run -d \
  --name "${PROD_CONTAINER}" \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"
sleep 8
curl -sS -o /dev/null -w 'root=%{http_code}\n' http://127.0.0.1/
curl -fsS http://127.0.0.1/api/status | python3 -c 'import sys,json; s=json.load(sys.stdin); print("ready", s.get("ready"), "backend", s.get("rag_backend"))'
sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}"
echo "cutover_from=${PROD_IMAGE} to=${IMAGE_TAG}"
