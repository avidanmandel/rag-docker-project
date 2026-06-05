#!/usr/bin/env bash
# Safe EC2 cutover: enable Recruitment Advisor on production host without breaking v14.
# Run on EC2 only. Requires .env (existing) and .env.agent (local on host, never commit).
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-session-docs-release}"
RUNTIME_DIR="${RUNTIME_DIR:-/home/ubuntu/scoutmatch-ai-runtime}"
IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:agent-extension-v15}"
ROLLBACK_TAG="${ROLLBACK_TAG:-scoutmatch-ai:baseline-club-v14}"
CANDIDATE="${CANDIDATE:-scoutmatch-ai-agent-extension-v15-candidate}"
CAND_RUNTIME="${CAND_RUNTIME:-/home/ubuntu/scoutmatch-ai-agent-extension-v15-runtime}"
PROD_CONTAINER="${PROD_CONTAINER:-scoutmatch-ai}"
BRANCH="${BRANCH:-feature/scoutmatch-agent-flow-extension}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="/tmp/recruitment_advisor_ec2_preflight_${TS}.log"

if [ ! -f "${APP_DIR}/.env" ]; then
  echo "MISSING_ENV=${APP_DIR}/.env"
  exit 1
fi
if [ ! -f "${APP_DIR}/.env.agent" ]; then
  echo "MISSING_ENV_AGENT=${APP_DIR}/.env.agent"
  echo "Create .env.agent on EC2 with SCOUTMATCH_AGENT_EXTENSION_ENABLED=true and agent IDs."
  exit 1
fi

cd "${APP_DIR}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "ec2-advisor-preserve-${TS}" || true
fi
git pull --ff-only origin "${BRANCH}"
echo "EC2_HEAD=$(git rev-parse HEAD)"
echo "PROD_BEFORE=$(sudo docker inspect -f '{{.Config.Image}}' ${PROD_CONTAINER})"

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${CAND_RUNTIME}"
mkdir -p "${CAND_RUNTIME}"
sudo docker build -t "${IMAGE_TAG}" .

sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5002:5000 \
  --env-file "${APP_DIR}/.env" \
  --env-file "${APP_DIR}/.env.agent" \
  -v "${CAND_RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  -e SCOUTMATCH_AGENT_EXTENSION_ENABLED=true \
  "${IMAGE_TAG}"

for i in $(seq 1 40); do
  curl -fsS http://127.0.0.1:5002/api/health >/dev/null 2>&1 && break
  sleep 3
done

set +e
{
  echo "=== health ==="
  curl -fsS http://127.0.0.1:5002/api/health
  echo
  echo "=== status ==="
  curl -fsS http://127.0.0.1:5002/api/status
  echo
  echo "=== homepage ==="
  curl -fsS -o /dev/null -w "home_http=%{http_code}\n" http://127.0.0.1:5002/
  echo "=== advisor page ==="
  curl -fsS -o /dev/null -w "advisor_http=%{http_code}\n" http://127.0.0.1:5002/recruitment-advisor
  echo "=== advisor status ==="
  curl -fsS http://127.0.0.1:5002/api/recruitment-advisor/status
  echo
} 2>&1 | tee "${LOG}"
PREFLIGHT_EXIT=${PIPESTATUS[0]}
set -e

if [ "${PREFLIGHT_EXIT}" -ne 0 ]; then
  echo "CANDIDATE_VALIDATION_FAILED exit=${PREFLIGHT_EXIT}"
  sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
  rm -rf "${CAND_RUNTIME}"
  exit 1
fi

echo "=== CUTOVER ==="
sudo docker rm -f "${PROD_CONTAINER}" >/dev/null 2>&1 || true
sudo docker run -d \
  --name "${PROD_CONTAINER}" \
  -p 0.0.0.0:80:5000 \
  --env-file "${APP_DIR}/.env" \
  --env-file "${APP_DIR}/.env.agent" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  -e SCOUTMATCH_AGENT_EXTENSION_ENABLED=true \
  --restart unless-stopped \
  "${IMAGE_TAG}"

for i in $(seq 1 40); do
  curl -fsS http://127.0.0.1:80/api/health >/dev/null 2>&1 && break
  sleep 3
done
curl -fsS http://127.0.0.1:80/api/health
echo
curl -fsS -o /dev/null -w "public_advisor_http=%{http_code}\n" http://127.0.0.1:80/recruitment-advisor
sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${CAND_RUNTIME}"

echo "CUTOVER_OK image=${IMAGE_TAG}"
echo "ROLLBACK: sudo docker rm -f ${PROD_CONTAINER}; sudo docker run -d --name ${PROD_CONTAINER} -p 0.0.0.0:80:5000 --env-file ${APP_DIR}/.env -v ${RUNTIME_DIR}:/app/runtime -e DATABASE_PATH=/app/runtime/chat.db -e BASELINE_KNOWLEDGE_ENABLED=true -e AWS_BASELINE_SET_ID=production --restart unless-stopped ${ROLLBACK_TAG}"
