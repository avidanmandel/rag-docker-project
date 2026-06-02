#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
ENV_FILE="${APP_DIR}/.env"
IMAGE_TAG="scoutmatch-ai:session-docs-v9"
CANDIDATE="scoutmatch-ai-v9-release-audit-candidate"
RUNTIME="/home/ubuntu/scoutmatch-ai-v9-release-audit-runtime"
LOG_FILE="/tmp/strict_release_audit.log"
PROD_CONTAINER="scoutmatch-ai"

# Remove any prior audit or validation candidates on loopback port 5001.
for old in scoutmatch-ai-v9-full-validation-candidate scoutmatch-ai-v9-release-audit-candidate; do
  sudo docker rm -f "${old}" >/dev/null 2>&1 || true
done

export IMAGE_TAG CANDIDATE RUNTIME LOG_FILE STRICT_AUDIT=1
bash "${APP_DIR}/scripts/run_full_live_validation_v8.sh"
AUDIT_EXIT=$?

echo "=== PRODUCTION UNCHANGED CHECK ==="
PROD_IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}")
echo "production_image=${PROD_IMAGE}"
for url in "http://127.0.0.1/" "http://127.0.0.1/api/health" "http://127.0.0.1/api/status"; do
  echo "public_${url##*/}=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done

exit "${AUDIT_EXIT}"
