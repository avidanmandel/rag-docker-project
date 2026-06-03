#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
RUNTIME_DIR="/home/ubuntu/scoutmatch-ai-runtime"
IMAGE_TAG="scoutmatch-ai:baseline-club-v14"
ROLLBACK_TAG="scoutmatch-ai:baseline-club-v13"
CANDIDATE="scoutmatch-ai-baseline-club-v14-candidate"
CAND_RUNTIME="/home/ubuntu/scoutmatch-ai-baseline-club-v14-runtime"
PROD_CONTAINER="scoutmatch-ai"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="/tmp/final_targeted_preflight_v14.log"

cd "${APP_DIR}"
git fetch origin feature/session-scoped-documents
git checkout feature/session-scoped-documents
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "ec2-local-preserve-${TS}" || true
fi
git pull --ff-only origin feature/session-scoped-documents
echo "EC2_HEAD=$(git rev-parse HEAD)"
echo "PROD_BEFORE=$(sudo docker inspect -f '{{.Config.Image}}' ${PROD_CONTAINER})"

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${CAND_RUNTIME}"
mkdir -p "${CAND_RUNTIME}"
sudo docker build -t "${IMAGE_TAG}" .

sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${CAND_RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  "${IMAGE_TAG}"

for i in $(seq 1 40); do
  curl -fsS http://127.0.0.1:5001/api/health >/dev/null 2>&1 && break
  sleep 3
done

echo "=== PHASE: SEED BASELINE ON CANDIDATE ==="
sudo docker exec \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${CANDIDATE}" \
  python scripts/seed_baseline_club_knowledge.py --apply --baseline-set-id production
for i in $(seq 1 60); do
  READY=$(curl -fsS http://127.0.0.1:5001/api/status | python3 -c 'import sys,json; s=json.load(sys.stdin); print("1" if s.get("baseline_ready") else "0")')
  DOCS=$(curl -fsS http://127.0.0.1:5001/api/status | python3 -c 'import sys,json; print(json.load(sys.stdin).get("baseline_document_count") or 0)')
  echo "baseline_poll_${i} ready=${READY} docs=${DOCS}"
  if [ "${READY}" = "1" ] && [ "${DOCS}" -ge 10 ]; then
    break
  fi
  sleep 5
done
curl -fsS http://127.0.0.1:5001/api/status | python3 -c 'import sys,json; s=json.load(sys.stdin); print("baseline_ready",s.get("baseline_ready"),"baseline_docs",s.get("baseline_document_count"),"baseline_sync",s.get("baseline_sync_state"))'
if ! curl -fsS http://127.0.0.1:5001/api/status | python3 -c 'import sys,json; s=json.load(sys.stdin); import sys as _s; _s.exit(0 if s.get("baseline_ready") else 1)'; then
  echo "BASELINE_SEED_NOT_READY"
  sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
  rm -rf "${CAND_RUNTIME}"
  exit 1
fi

set +e
python3 scripts/final_targeted_preflight.py http://127.0.0.1:5001 --skip-public 2>&1 | tee "${LOG}"
PREFLIGHT_EXIT=${PIPESTATUS[0]}
set -e
if [ "${PREFLIGHT_EXIT}" -ne 0 ]; then
  echo "CANDIDATE_VALIDATION_FAILED exit=${PREFLIGHT_EXIT}"
  sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
  rm -rf "${CAND_RUNTIME}"
  exit 1
fi
if ! grep -q '^BLOCKERS=0' "${LOG}"; then
  echo "CANDIDATE_VALIDATION_BLOCKERS"
  sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
  rm -rf "${CAND_RUNTIME}"
  exit 1
fi
echo "CANDIDATE_VALIDATION_PASSED"

mkdir -p "${RUNTIME_DIR}/rollback"
BACKUP="${RUNTIME_DIR}/rollback/chat.db.${TS}.bak"
sudo cp "${RUNTIME_DIR}/chat.db" "${BACKUP}"
sudo chown ubuntu:ubuntu "${BACKUP}"
echo "DB_BACKUP=${BACKUP}"

PROD_IMAGE=$(sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}")
sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
sudo docker rm -f "${PROD_CONTAINER}" >/dev/null 2>&1 || true
sudo docker run -d \
  --name "${PROD_CONTAINER}" \
  --restart unless-stopped \
  -p 0.0.0.0:80:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${RUNTIME_DIR}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  -e BASELINE_KNOWLEDGE_ENABLED=true \
  -e AWS_BASELINE_SET_ID=production \
  "${IMAGE_TAG}"
sleep 12
echo "PROD_AFTER=$(sudo docker inspect -f '{{.Config.Image}}' ${PROD_CONTAINER})"
echo "CUTOVER_FROM=${PROD_IMAGE}"

curl -fsS http://127.0.0.1/api/status | python3 -c 'import sys,json; s=json.load(sys.stdin); print("ready",s.get("ready"),"baseline_ready",s.get("baseline_ready"),"ingestion",(s.get("latest_ingestion") or {}).get("status"))'

set +e
python3 scripts/final_targeted_preflight.py http://127.0.0.1 --skip-public 2>&1 | tee "/tmp/public_lifecycle_v14.log"
PUBLIC_EXIT=${PIPESTATUS[0]}
set -e
if [ "${PUBLIC_EXIT}" -ne 0 ] || ! grep -q '^BLOCKERS=0' "/tmp/public_lifecycle_v14.log"; then
  echo "PUBLIC_VALIDATION_FAILED"
  exit 1
fi
echo "PUBLIC_VALIDATION_PASSED"

rm -rf "${CAND_RUNTIME}"
sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
sudo docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "${PROD_CONTAINER}"
echo "ROLLBACK_TAG=${ROLLBACK_TAG}"

if [ -f scripts/audit_cleanup_leftover.py ]; then
  python3 scripts/audit_cleanup_leftover.py 2>/dev/null | tail -5 || true
fi
