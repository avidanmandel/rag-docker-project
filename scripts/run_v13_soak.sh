#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-session-docs-release}"
export APP_DIR
export IMAGE_TAG="${IMAGE_TAG:-scoutmatch-ai:baseline-club-v13}"
export CANDIDATE="${CANDIDATE:-scoutmatch-ai-baseline-v13-soak-candidate}"
export RUNTIME="${RUNTIME:-/home/ubuntu/scoutmatch-ai-baseline-v13-soak-runtime}"
export BASELINE_SET_ID="${BASELINE_SET_ID:-candidate-soak-$(date +%Y%m%d%H%M%S)}"
export SOAK_CYCLE_DELAY="${SOAK_CYCLE_DELAY:-480}"
export SOAK_MAX_INGEST="${SOAK_MAX_INGEST:-50}"

cd "${APP_DIR}"
mkdir -p "${APP_DIR}/artifacts/logs"

LOCK="${APP_DIR}/artifacts/logs/v13_soak.lock"
if [ -f "${LOCK}" ]; then
  old_pid="$(cat "${LOCK}" 2>/dev/null || true)"
  if [ -n "${old_pid}" ] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "Another soak runner is active (pid=${old_pid})"
    exit 1
  fi
fi
echo "$$" > "${LOCK}"
trap 'rm -f "${LOCK}"' EXIT

exec python3 "${APP_DIR}/scripts/run_v13_soak.py"
