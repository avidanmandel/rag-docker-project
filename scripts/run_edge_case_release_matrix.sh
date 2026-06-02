#!/usr/bin/env bash
# Run local release gate checks: unit tests, fixture validation, optional strict matrix.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "=== EDGE-CASE RELEASE MATRIX (local) ==="
python -m pytest tests/test_scoutmatch.py -q --tb=no
python scripts/validate_release_fixtures.py
echo "local_matrix=PASS"
