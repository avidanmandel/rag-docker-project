# Business Acceptance Matrix

Automated business-logic, multi-format, lifecycle, session-isolation, and AWS acceptance gate for ScoutMatch AI.

## Fixtures

| Dataset | Purpose | Location |
|---------|---------|----------|
| A | Core player matrix (12 files, salary total 471,000 EUR) | `tests/fixtures/business_acceptance/` |
| B | Tactical role matrix (5 files) | same |
| C | Format validation (8 files + verification codes) | same |
| D | Invalid / duplicate / update inputs | same |

Generate or refresh:

```bash
python scripts/generate_business_acceptance_fixtures.py
```

Manifest: `tests/fixtures/business_acceptance/manifest.json`

## Runner

Local (requires running candidate at loopback):

```bash
python scripts/run_business_acceptance_gate.py --strict http://127.0.0.1:5001
```

EC2 loopback candidate:

```bash
IMAGE_TAG=scoutmatch-ai:session-docs-v11 \
CANDIDATE=scoutmatch-ai-v11-business-gate-candidate \
RUNTIME=/home/ubuntu/scoutmatch-ai-v11-business-gate-runtime \
bash scripts/run_business_acceptance_gate.sh
```

## Mandatory test categories

| ID prefix | Category |
|-----------|----------|
| BA-UI | Static UI checks (no browser automation) |
| BA-END | Endpoint / status / asset checks |
| BA-FMT | TXT, PDF, DOCX, CSV, quoted CSV, BOM, Unicode, spaces |
| BA-PLR | Single-player EN/HE, salary, height non-hallucination, unknown |
| BA-AGG | Exact aggregates (relocation, salary, defenders, immediate) |
| BA-FLT | Filters (budget, left foot, GK, cheapest, RB) |
| BA-REC | Recommendations (team + tactical requirements) |
| BA-REF | Refusal / unrelated file exclusion |
| BA-INJ | Prompt injection resistance |
| BA-DUP / BA-UPD | Duplicates and content updates |
| BA-LC | Document lifecycle (delete one, clear, stale) |
| BA-ISO | Session A/B isolation |
| BA-SYNC | Sync contention |
| BA-INV | Invalid inputs (4xx, no revision bump) |

Persistence restart, remove/recreate with same mount, and `reconcile_session_documents.py --dry-run` run in the EC2 shell wrapper after the Python gate.

## Expected Dataset A aggregates

- **Relocation YES (6):** Or David, Pedro Silva, Amit Levy, Luca Romano, Miguel Santos, Daniel Cohen
- **Immediate (6):** Pedro Silva, Luca Romano, Noam David, Miguel Santos, Daniel Cohen, Marco Silva
- **Defenders (3):** Amit Levy, Luca Romano, Noam David
- **Left foot (2):** Pedro Silva, Luca Romano
- **Salary total:** 471,000 EUR (each unique CV once; scouting report excluded)
- **Forward ≤50k:** Pedro Silva

## Rollback

Production rollback image: `scoutmatch-ai:session-docs-v10`.

v11 cutover performed 2026-06-02 after mandatory gate **BLOCKERS 0** (`/tmp/business_gate_v11_iter3.log`).
