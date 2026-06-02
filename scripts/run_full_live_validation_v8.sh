#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
ENV_FILE="${APP_DIR}/.env"
IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:session-docs-v8}"
CANDIDATE="${CANDIDATE:-scoutmatch-ai-v8-full-validation-candidate}"
RUNTIME="${RUNTIME:-/home/ubuntu/scoutmatch-ai-v8-full-validation-runtime}"
BASE="http://127.0.0.1:5001"
PROD_CONTAINER="scoutmatch-ai"
BUCKET=$(grep '^AWS_S3_BUCKET=' "${ENV_FILE}" | cut -d= -f2-)

cd "${APP_DIR}"
git fetch origin feature/session-scoped-documents
git checkout feature/session-scoped-documents
git pull --ff-only origin feature/session-scoped-documents || true

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

python3 "${APP_DIR}/scripts/full_live_validation_matrix.py" "${BASE}" | tee /tmp/full_live_validation_v8.log || true
VALIDATION_EXIT=${PIPESTATUS[0]:-0}

SESSION_B=$(grep '^SESSION_B ' /tmp/full_live_validation_v8.log | awk '{print $2}' || true)
SESSION_A=$(grep '^SESSION_A ' /tmp/full_live_validation_v8.log | awk '{print $2}' || true)
SESSION_C=$(grep '^SESSION_C ' /tmp/full_live_validation_v8.log | awk '{print $2}' || true)

echo "=== PHASE 11: PERSISTENCE RESTART ==="
sudo docker restart "${CANDIDATE}" >/dev/null
sleep 12
if [ -n "${SESSION_B}" ]; then
  curl -fsS "${BASE}/api/sessions/${SESSION_B}" | python3 -c 'import sys,json; s=json.load(sys.stdin); print("restart_persist", s.get("id"), s.get("sync_state"), s.get("document_revision"))'
fi

echo "=== PHASE 11B: REMOVE/RECREATE WITH SAME MOUNT ==="
sudo docker rm -f "${CANDIDATE}" >/dev/null
sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${ENV_FILE}" \
  -v "${RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"
sleep 12
if [ -n "${SESSION_B}" ]; then
  curl -fsS "${BASE}/api/sessions/${SESSION_B}" | python3 -c 'import sys,json; s=json.load(sys.stdin); print("recreate_persist", s.get("id"), s.get("sync_state"), s.get("document_revision"))'
fi

echo "=== PHASE 12: RECONCILE ==="
sudo docker exec "${CANDIDATE}" python scripts/reconcile_session_documents.py --dry-run | tee /tmp/reconcile_v8.log

echo "=== PHASE 13: CLEANUP ==="
for sid in "${SESSION_A}" "${SESSION_B}" "${SESSION_C}"; do
  [ -z "${sid}" ] && continue
  curl -sS -X DELETE "${BASE}/api/sessions/${sid}" \
    -H 'Content-Type: application/json' \
    -d '{"delete_documents": true}' >/dev/null 2>&1 || true
done

LEFT_TOTAL=0
for sid in "${SESSION_A}" "${SESSION_B}" "${SESSION_C}"; do
  [ -z "${sid}" ] && continue
  COUNT=$(aws s3 ls "s3://${BUCKET}/scoutmatch/knowledge-base/sessions/${sid}/" 2>/dev/null | wc -l || echo 0)
  echo "leftover_${sid}=${COUNT}"
  LEFT_TOTAL=$((LEFT_TOTAL + COUNT))
done
echo "final_disposable_s3_keys=${LEFT_TOTAL}"

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${RUNTIME}"

echo "=== PRODUCTION CHECK ==="
PROD_IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}")
echo "production_image=${PROD_IMAGE}"
for url in "http://127.0.0.1/" "http://127.0.0.1/api/health" "http://127.0.0.1/api/status"; do
  echo "public_${url##*/}=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done

exit "${VALIDATION_EXIT}"
