#!/usr/bin/env bash
set -euo pipefail
PUBLIC="${PUBLIC:-http://127.0.0.1}"
APP_DIR="/home/ubuntu/scoutmatch-ai-session-docs-release"
BUCKET=$(grep '^AWS_S3_BUCKET=' "${APP_DIR}/.env" | cut -d= -f2-)

echo "=== PUBLIC ENDPOINTS ==="
for url in "${PUBLIC}/" "${PUBLIC}/api/health" "${PUBLIC}/api/status" "${PUBLIC}/static/images/home-dashboard-art.png"; do
  echo "$(basename "${url}")=$(curl -sS -o /dev/null -w '%{http_code}' "${url}")"
done
curl -fsS "${PUBLIC}/api/status" | python3 -c 'import sys,json; s=json.load(sys.stdin); print("ready", s.get("ready"), "engine", s.get("engine_class"))'
sudo docker inspect -f '{{.Config.Image}}' scoutmatch-ai

echo "=== RECONCILE DRY-RUN (container) ==="
sudo docker exec scoutmatch-ai python scripts/reconcile_session_documents.py --dry-run 2>&1 | head -40

echo "=== PUBLIC VALIDATION SESSION ==="
SID=$(curl -fsS -X POST "${PUBLIC}/api/sessions" -H 'Content-Type: application/json' -d '{}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "session=${SID}"

upload() {
  curl -fsS -X POST "${PUBLIC}/api/sessions/${SID}/documents/upload" -F "file=@$1" >/dev/null
}

printf 'Full Name: Public Striker\nPosition: Forward\nSalary: 90000 EUR\nRelocation: YES\nAvailability: Immediate\nPreferred Foot: Right\n' >/tmp/pub_player.txt
printf 'Full Name: Public Defender\nPosition: Defender\nSalary: 60000 EUR\nRelocation: NO\n' >/tmp/pub_defender.txt
printf 'passenger,survived\n1,0\n2,1\n' >/tmp/titanic.csv

upload /tmp/pub_player.txt
upload /tmp/pub_defender.txt
upload /tmp/titanic.csv

wait_ready() {
  local label="$1"
  for i in $(seq 1 12); do
    ST=$(curl -fsS "${PUBLIC}/api/sessions/${SID}" | python3 -c 'import sys,json; s=json.load(sys.stdin); print(s.get("sync_state"), s.get("document_revision"), s.get("synced_revision"))')
    echo "${label}_${i}=${ST}"
    echo "${ST}" | grep -q "READY" && return 0
    sleep 5
  done
  return 1
}

wait_ready sync_check

SP=$(curl -fsS -X POST "${PUBLIC}/api/sessions/${SID}/messages" -H 'Content-Type: application/json' -d '{"content":"What is Public Striker salary?"}')
echo "${SP}" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("single_player_refused", r.get("refused"), "sources", len(r.get("sources") or []), "has_salary", "90000" in (r.get("content") or ""))'

AG=$(curl -fsS -X POST "${PUBLIC}/api/sessions/${SID}/messages" -H 'Content-Type: application/json' -d '{"content":"Show all candidates willing to relocate"}')
echo "${AG}" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("aggregate_reloc_refused", r.get("refused"), "sources", len(r.get("sources") or []))'

ST=$(curl -fsS -X POST "${PUBLIC}/api/sessions/${SID}/messages" -H 'Content-Type: application/json' -d '{"content":"What is the total annual salary of all uploaded players?"}')
echo "${ST}" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("salary_total_refused", r.get("refused"), "sources", len(r.get("sources") or []), "mentions_150000", "150000" in (r.get("content") or ""))'

TI=$(curl -fsS -X POST "${PUBLIC}/api/sessions/${SID}/messages" -H 'Content-Type: application/json' -d '{"content":"What happened to the Titanic ship disaster?"}')
echo "${TI}" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("titanic_refused", r.get("refused"), "sources", len(r.get("sources") or []))'

DOC_ID=$(curl -fsS "${PUBLIC}/api/sessions/${SID}/documents" | python3 -c 'import sys,json; docs=json.load(sys.stdin); print(next((d["id"] for d in docs if "titanic" in d.get("display_name","").lower()), docs[0]["id"]))')
curl -fsS -X DELETE "${PUBLIC}/api/sessions/${SID}/documents/${DOC_ID}" >/dev/null
wait_ready after_delete_sync

curl -fsS -X DELETE "${PUBLIC}/api/sessions/${SID}/documents" >/dev/null
wait_ready after_clear_sync

CLR=$(curl -fsS -X POST "${PUBLIC}/api/sessions/${SID}/messages" -H 'Content-Type: application/json' -d '{"content":"What is Public Striker salary?"}')
echo "${CLR}" | python3 -c 'import sys,json; r=json.load(sys.stdin); print("after_clear_refused", r.get("refused"), "sources", len(r.get("sources") or []))'

curl -fsS -X DELETE "${PUBLIC}/api/sessions/${SID}" -H 'Content-Type: application/json' -d '{"delete_documents": true}' >/dev/null
LEFT=$(aws s3 ls "s3://${BUCKET}/scoutmatch/knowledge-base/sessions/${SID}/" 2>/dev/null | wc -l || echo 0)
echo "final_leftover_keys=${LEFT}"
