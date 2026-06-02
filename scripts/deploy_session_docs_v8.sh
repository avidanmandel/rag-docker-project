#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
RUNTIME_DIR="/home/ubuntu/scoutmatch-ai-runtime"
IMAGE_TAG="scoutmatch-ai:session-docs-v8"
ROLLBACK_TAG="scoutmatch-ai:session-docs-v7"
PROD_CONTAINER="scoutmatch-ai"
CANDIDATE="scoutmatch-ai-candidate"
AUDIT_RUNTIME="/home/ubuntu/scoutmatch-ai-rag-v8-runtime"
BASE="http://127.0.0.1:5001"
PUBLIC="http://127.0.0.1"
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
sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true
rm -rf "${AUDIT_RUNTIME}"
mkdir -p "${AUDIT_RUNTIME}"
sudo docker run -d \
  --name "${CANDIDATE}" \
  -p 127.0.0.1:5001:5000 \
  --env-file "${APP_DIR}/.env" \
  -v "${AUDIT_RUNTIME}:/app/runtime" \
  -e DATABASE_PATH=/app/runtime/chat.db \
  "${IMAGE_TAG}"
sleep 12

for url in "${BASE}/" "${BASE}/api/health" "${BASE}/api/status"; do
  echo "candidate_$(basename "${url}")=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done
curl -fsS "${BASE}/api/status" | python3 -c 'import sys,json; s=json.load(sys.stdin); print(s.get("rag_backend"), s.get("engine_class"), s.get("ready"))'

BUCKET=$(grep '^AWS_S3_BUCKET=' "${APP_DIR}/.env" | cut -d= -f2-)
SID=$(curl -fsS -X POST "${BASE}/api/sessions" -H 'Content-Type: application/json' -d '{}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

upload_file() {
  local file="$1"
  curl -sS -o "/tmp/v8_up.json" -w "%{http_code}" \
    -X POST "${BASE}/api/sessions/${SID}/documents/upload" \
    -F "file=@${file}"
}

printf 'Full Name: Audit Striker One\nPosition: Forward\nSalary: 80000 EUR\nRelocation: YES\n' >/tmp/v8_player.txt
echo "upload1=$(upload_file /tmp/v8_player.txt)"

# duplicate upload should return 200 duplicate
echo "duplicate=$(upload_file /tmp/v8_player.txt)"

# Titanic refusal
TITANIC_RESP=$(curl -fsS -X POST "${BASE}/api/sessions/${SID}/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content":"What happened to the Titanic ship disaster?"}')
echo "${TITANIC_RESP}" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("titanic_refused", r.get("refused"), "sources", len(r.get("sources") or []))'

# Delete conversation
DEL=$(curl -sS -o /tmp/v8_del.json -w "%{http_code}" -X DELETE "${BASE}/api/sessions/${SID}" \
  -H 'Content-Type: application/json' -d '{"delete_documents": true}')
echo "delete_http=${DEL}"
LEFT=$(aws s3 ls "s3://${BUCKET}/scoutmatch/knowledge-base/sessions/${SID}/" 2>/dev/null | wc -l || echo 0)
echo "leftover_keys=${LEFT}"

sudo docker rm -f "${CANDIDATE}" >/dev/null 2>&1 || true

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

for url in "${PUBLIC}/" "${PUBLIC}/api/health" "${PUBLIC}/api/status" "${PUBLIC}/static/images/home-dashboard-art.png"; do
  echo "public_$(basename "${url}")=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done
curl -fsS "${PUBLIC}/api/status" | python3 -c 'import sys,json; s=json.load(sys.stdin); print("ready", s.get("ready"))'
sudo docker inspect -f '{{.Config.Image}}' "${PROD_CONTAINER}"

PUB_SID=$(curl -fsS -X POST "${PUBLIC}/api/sessions" -H 'Content-Type: application/json' -d '{}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
printf 'Public audit player\nSalary 70000 EUR\n' >/tmp/v8_pub.txt
curl -fsS -X POST "${PUBLIC}/api/sessions/${PUB_SID}/documents/upload" -F "file=@/tmp/v8_pub.txt" >/dev/null
curl -fsS -X DELETE "${PUBLIC}/api/sessions/${PUB_SID}" -H 'Content-Type: application/json' -d '{"delete_documents": true}' >/dev/null
PUB_LEFT=$(aws s3 ls "s3://${BUCKET}/scoutmatch/knowledge-base/sessions/${PUB_SID}/" 2>/dev/null | wc -l || echo 0)
echo "public_leftover=${PUB_LEFT}"
echo "cutover_from=${PROD_IMAGE} to=${IMAGE_TAG}"
