#!/usr/bin/env bash
# Build a clean submission ZIP excluding secrets, logs, and local-only artifacts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/dist"
NAME="Avidan_RAG_Docker_Project-submission"
ZIP="${OUT}/${NAME}.zip"
mkdir -p "${OUT}"
rm -f "${ZIP}"

cd "${ROOT}"
zip -r "${ZIP}" . \
  -x "./.git/*" \
  -x "./.env" -x "./.env.*" -x "!./.env.example" -x "!./.env.ec2.example" \
  -x "./*.pem" -x "./*.key" -x "./.aws/*" \
  -x "./artifacts/logs/*" -x "./*.log" \
  -x "./runtime/*" -x "./data/*" -x "./index_cache/*" \
  -x "./*chat.db" -x "./*.db" \
  -x "./.venv/*" -x "./venv/*" \
  -x "./__pycache__/*" -x "./*/__pycache__/*" \
  -x "./home-preview-*.png" \
  -x "./scripts/deploy_session_docs_v3.sh" \
  -x "./scripts/deploy_session_docs_v4.sh" \
  -x "./scripts/deploy_session_docs_v5.sh" \
  -x "./scripts/deploy_session_docs_v6.sh" \
  -x "./scripts/deploy_session_docs_v7.sh" \
  -x "./scripts/audit_*.py" -x "./scripts/audit_*.sh" \
  -x "./dist/*"

echo "submission_zip=${ZIP}"
ls -lh "${ZIP}"
