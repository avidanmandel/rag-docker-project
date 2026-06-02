#!/usr/bin/env bash
# Read-only AWS cleanup report — never deletes resources.
set -euo pipefail
APP_DIR="${APP_DIR:-/home/ubuntu/scoutmatch-ai-session-docs-release}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
BUCKET=$(grep '^AWS_S3_BUCKET=' "${ENV_FILE}" | cut -d= -f2-)
PREFIX=$(grep '^AWS_S3_PREFIX=' "${ENV_FILE}" | cut -d= -f2-)
PREFIX="${PREFIX:-scoutmatch/knowledge-base/}"

echo "=== AWS CLEANUP DRY-RUN ==="
echo "bucket=${BUCKET}"
echo "prefix=${PREFIX}"
echo "mode=dry_run_only"

echo "--- disposable session prefixes (sample list) ---"
aws s3 ls "s3://${BUCKET}/${PREFIX}sessions/" 2>/dev/null | head -20 || echo "no_session_prefix_listing"

echo "--- reconcile (container) ---"
if sudo docker ps --format '{{.Names}}' | grep -qx scoutmatch-ai; then
  sudo docker exec scoutmatch-ai python scripts/reconcile_session_documents.py --dry-run || true
else
  echo "production_container_not_running"
fi

echo "--- candidate containers ---"
sudo docker ps -a --format '{{.Names}} {{.Image}}' | grep -E 'candidate|scoutmatch-ai' || true

echo "DRY_RUN_COMPLETE no_deletions_performed"
