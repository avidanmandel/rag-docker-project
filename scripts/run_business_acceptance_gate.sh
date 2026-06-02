#!/usr/bin/env bash
set -euo pipefail
# LF line endings required for EC2 bash

APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-session-docs-release}"
ENV_FILE="${APP_DIR}/.env"
IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:session-docs-v10}"
CANDIDATE="${CANDIDATE:-scoutmatch-ai-v10-business-gate-candidate}"
RUNTIME="${RUNTIME:-/home/ubuntu/scoutmatch-ai-v10-business-gate-runtime}"
BASE="http://127.0.0.1:5001"
PROD_CONTAINER="scoutmatch-ai"
BUCKET=$(grep '^AWS_S3_BUCKET=' "${ENV_FILE}" | cut -d= -f2-)
LOG_DIR="${APP_DIR}/artifacts/logs"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/business_acceptance_gate_$(date +%Y%m%d_%H%M%S).log}"

mkdir -p "${LOG_DIR}"

cd "${APP_DIR}"
git fetch origin feature/session-scoped-documents 2>/dev/null || true
git checkout feature/session-scoped-documents 2>/dev/null || true
git pull --ff-only origin feature/session-scoped-documents 2>/dev/null || true

python3 "${APP_DIR}/scripts/generate_business_acceptance_fixtures.py"

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${RUNTIME}"
mkdir -p "${RUNTIME}"

sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${ENV_FILE}" \
  -v "${RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"

echo "Waiting for candidate health..."
for i in $(seq 1 24); do
  if curl -fsS "${BASE}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

GATE_ARGS=(--strict "${BASE}" "${APP_DIR}")
set +e
python3 "${APP_DIR}/scripts/run_business_acceptance_gate.py" "${GATE_ARGS[@]}" 2>&1 | tee "${LOG_FILE}"
GATE_EXIT=${PIPESTATUS[0]}
set -e

echo "=== GATE SUMMARY ==="
grep '^BLOCKERS ' "${LOG_FILE}" || echo "BLOCKERS (missing)"
grep '^BLOCKER ' "${LOG_FILE}" || true

PERSIST_SESSION=$(grep '^SESSION_ISO_B ' "${LOG_FILE}" | tail -1 | awk '{print $2}' || true)
PERSIST_SESSION="${PERSIST_SESSION:-$(grep '^SESSION_A ' "${LOG_FILE}" | tail -1 | awk '{print $2}' || true)}"

echo "=== PERSISTENCE RESTART ==="
sudo docker restart "${CANDIDATE}" >/dev/null
sleep 12
if [ -n "${PERSIST_SESSION}" ]; then
  HTTP_CODE=$(curl -sS -o /tmp/business_gate_persist.json -w '%{http_code}' "${BASE}/api/sessions/${PERSIST_SESSION}" || echo "000")
  echo "restart_persist_http=${HTTP_CODE}"
fi

echo "=== REMOVE/RECREATE WITH SAME MOUNT ==="
sudo docker rm -f "${CANDIDATE}" >/dev/null
sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${ENV_FILE}" \
  -v "${RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"
sleep 12
if [ -n "${PERSIST_SESSION}" ]; then
  HTTP_CODE=$(curl -sS -o /tmp/business_gate_persist.json -w '%{http_code}' "${BASE}/api/sessions/${PERSIST_SESSION}" || echo "000")
  echo "recreate_persist_http=${HTTP_CODE}"
fi

echo "=== RECONCILE DRY-RUN ==="
sudo docker exec "${CANDIDATE}" python scripts/reconcile_session_documents.py --dry-run | tee /tmp/business_gate_reconcile.log

echo "=== CLEANUP DISPOSABLE SESSIONS ==="
grep '^DISPOSABLE_SESSION ' "${LOG_FILE}" | awk '{print $2}' | while read -r sid; do
  [ -z "${sid}" ] && continue
  curl -sS -X DELETE "${BASE}/api/sessions/${sid}" \
    -H 'Content-Type: application/json' \
    -d '{"delete_documents": true}' >/dev/null 2>&1 || true
done

LEFT_TOTAL=0
grep '^DISPOSABLE_SESSION ' "${LOG_FILE}" | awk '{print $2}' | while read -r sid; do
  [ -z "${sid}" ] && continue
  COUNT=$(timeout 45 aws s3 ls "s3://${BUCKET}/scoutmatch/knowledge-base/sessions/${sid}/" 2>/dev/null | wc -l | tr -d ' ' || echo "timeout")
  echo "leftover_${sid}=${COUNT}"
done

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${RUNTIME}"

echo "=== PRODUCTION CHECK ==="
PROD_IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}")
echo "production_image=${PROD_IMAGE}"
for url in "http://127.0.0.1/" "http://127.0.0.1/api/health" "http://127.0.0.1/api/status" "http://127.0.0.1/static/images/home-dashboard-art.png"; do
  echo "public_${url##*/}=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done
echo "log_file=${LOG_FILE}"
echo "gate_exit=${GATE_EXIT}"

exit "${GATE_EXIT}"
