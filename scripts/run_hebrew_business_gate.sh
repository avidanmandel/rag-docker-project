#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-session-docs-release}"
IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:baseline-club-v13}"
CANDIDATE="${CANDIDATE:-scoutmatch-ai-baseline-v13-candidate}"
RUNTIME="${RUNTIME:-/home/ubuntu/scoutmatch-ai-baseline-v13-runtime}"
BASE="http://127.0.0.1:5001"
LOG_DIR="${APP_DIR}/artifacts/logs"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/hebrew_business_gate_$(date +%Y%m%d_%H%M%S).log}"

mkdir -p "${LOG_DIR}"
cd "${APP_DIR}"

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${RUNTIME}"
mkdir -p "${RUNTIME}"

sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  "${IMAGE_TAG}"

for i in $(seq 1 24); do
  curl -fsS "${BASE}/api/health" >/dev/null 2>&1 && break
  sleep 5
done

set +e
python3 "${APP_DIR}/scripts/run_hebrew_business_gate.py" --strict "${BASE}" 2>&1 | tee "${LOG_FILE}"
EXIT=${PIPESTATUS[0]}
set -e

grep '^DISPOSABLE_SESSION ' "${LOG_FILE}" | awk '{print $2}' | while read -r sid; do
  [ -z "${sid}" ] && continue
  curl -sS -X DELETE "${BASE}/api/sessions/${sid}" \
    -H 'Content-Type: application/json' \
    -d '{"delete_documents": true}' >/dev/null 2>&1 || true
done

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${RUNTIME}"
echo "hebrew_gate_exit=${EXIT}"
exit "${EXIT}"
