#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
RUNTIME_DIR="/home/ubuntu/scoutmatch-ai-runtime"
IMAGE_TAG="scoutmatch-ai:session-docs-v10"
ROLLBACK_TAG="scoutmatch-ai:session-docs-v9"
PROD_CONTAINER="scoutmatch-ai"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "${RUNTIME_DIR}/rollback"
sudo cp "${RUNTIME_DIR}/chat.db" "${RUNTIME_DIR}/rollback/chat.db.${TS}.bak"
sudo chown ubuntu:ubuntu "${RUNTIME_DIR}/rollback/chat.db.${TS}.bak"

cd "${APP_DIR}"
git fetch origin feature/session-scoped-documents
git checkout feature/session-scoped-documents
git pull --ff-only origin feature/session-scoped-documents
echo "Release commit: $(git rev-parse HEAD)"

sudo docker build -t "${IMAGE_TAG}" .

IMAGE_TAG="${IMAGE_TAG}" CANDIDATE="scoutmatch-ai-v10-full-validation-candidate" \
  RUNTIME="/home/ubuntu/scoutmatch-ai-v10-full-validation-runtime" \
  LOG_FILE="/tmp/full_live_validation_v10.log" \
  STRICT_AUDIT=1 \
  bash scripts/run_full_live_validation_v8.sh
VALIDATION_EXIT=$?
if [ "${VALIDATION_EXIT}" -ne 0 ]; then
  echo "CANDIDATE_VALIDATION_FAILED exit=${VALIDATION_EXIT}"
  exit 1
fi
if grep -qE '^BLOCKERS [1-9]' /tmp/full_live_validation_v10.log; then
  echo "CANDIDATE_VALIDATION_BLOCKERS"
  exit 1
fi
echo "CANDIDATE_VALIDATION_PASSED"

PROD_IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}")
sudo docker rm -f "${PROD_CONTAINER}" >/dev/null 2>&1 || true
sudo docker run -d \
  --name "${PROD_CONTAINER}" \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"
sleep 8

for url in "http://127.0.0.1/" "http://127.0.0.1/api/health" "http://127.0.0.1/api/status"; do
  echo "public_$(basename "${url}")=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done
curl -fsS "http://127.0.0.1/api/status" | python3 -c 'import sys,json; s=json.load(sys.stdin); print("ready", s.get("ready"))'
sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}"
echo "cutover_from=${PROD_IMAGE} rollback=${ROLLBACK_TAG} to=${IMAGE_TAG}"
