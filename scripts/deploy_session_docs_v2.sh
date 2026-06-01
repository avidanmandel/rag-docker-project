#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-runtime/repo}"
RUNTIME_DIR="${RUNTIME_DIR:-/home/ubuntu/scoutmatch-ai-runtime}"
IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:session-docs-v2}"
PROD_CONTAINER="${PROD_CONTAINER:-scoutmatch-ai}"
CANDIDATE_CONTAINER="${CANDIDATE_CONTAINER:-scoutmatch-ai-candidate}"
ROLLBACK_DIR="${RUNTIME_DIR}/rollback"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "${ROLLBACK_DIR}"
cp "${RUNTIME_DIR}/chat.db" "${ROLLBACK_DIR}/chat.db.${TS}.bak"

cd "${APP_DIR}"
git fetch origin feature/session-scoped-documents
git checkout feature/session-scoped-documents
git pull --ff-only origin feature/session-scoped-documents
RELEASE_COMMIT="$(git rev-parse HEAD)"
echo "Release commit: ${RELEASE_COMMIT}"

docker build -t "${IMAGE_TAG}" .

docker rm -f "${CANDIDATE_CONTAINER}" >/dev/null 2>&1 || true
docker run -d \
  --name "${CANDIDATE_CONTAINER}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"

sleep 8
curl -fsS http://127.0.0.1:5001/api/health >/dev/null
curl -fsS http://127.0.0.1:5001/api/status | grep -q aws_kb

docker exec "${CANDIDATE_CONTAINER}" python scripts/cleanup_accidental_test_document.py || true

PROD_IMAGE="$(docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}" 2>/dev/null || true)"
PROD_IMAGE_ID="$(docker inspect -f '{{.Image}}' "${PROD_CONTAINER}" 2>/dev/null || true)"
cat > "${ROLLBACK_DIR}/rollback.${TS}.env" <<EOF
PROD_CONTAINER=${PROD_CONTAINER}
PROD_IMAGE=${PROD_IMAGE}
PROD_IMAGE_ID=${PROD_IMAGE_ID}
ROLLBACK_DB=${ROLLBACK_DIR}/chat.db.${TS}.bak
EOF

docker rm -f "${CANDIDATE_CONTAINER}" >/dev/null 2>&1 || true

docker rm -f "${PROD_CONTAINER}" >/dev/null 2>&1 || true
docker run -d \
  --name "${PROD_CONTAINER}" \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"

echo "Deployed ${IMAGE_TAG} at commit ${RELEASE_COMMIT}"
