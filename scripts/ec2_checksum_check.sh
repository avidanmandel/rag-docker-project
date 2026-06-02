#!/usr/bin/env bash
set -euo pipefail
APP="/home/ubuntu/scoutmatch-ai-session-docs-release"
for f in app.py aws_kb_engine.py database.py requirement_verification.py aws_storage_service.py; do
  h1=$(sha256sum "${APP}/${f}" | awk '{print $1}')
  h2=$(sudo docker exec scoutmatch-ai sha256sum "/app/${f}" | awk '{print $1}')
  if [ "${h1}" = "${h2}" ]; then
    echo "${f} match"
  else
    echo "${f} MISMATCH"
  fi
done
