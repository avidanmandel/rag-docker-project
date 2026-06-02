# V13 bounded soak harness

Tooling-only soak runner for production sign-off. Does not modify application
source or deploy images.

## Run (EC2)

```bash
cd /home/ubuntu/scoutmatch-ai-session-docs-release
bash scripts/run_v13_soak.sh
```

Environment overrides:

- `BASELINE_SET_ID` — default `candidate-soak-<timestamp>`
- `SOAK_CYCLE_DELAY` — seconds between cycles (default `480`)
- `SOAK_MAX_INGEST` — max tracked ingestion jobs (default `50`)

## Cleanup disposable resources

Dry-run:

```bash
sudo docker exec scoutmatch-ai python scripts/cleanup_candidate_baseline_set.py \
  --auto-disposable-baselines --session-id <uuid>
```

Apply:

```bash
sudo docker exec scoutmatch-ai python scripts/cleanup_candidate_baseline_set.py \
  --apply --baseline-set-id candidate-soak-<timestamp> --session-id <uuid>
```

Production baseline (`production`) is never deleted by this script.

## Harness fixes (v13 soak repair)

- Baseline seed verifies S3 object SHA-256 before skipping upload when the
  SQLite registry matches the manifest (prevents tactical_summary-style drift).
- Baseline business gate requires `CANDIDATE` for loopback `:5001` seeding
  (uses `docker exec`, not host Python).
- Hebrew gate seeds the disposable `candidate-soak-*` set, not `production`.
- Soak runner uses one isolated candidate container, runtime, and baseline set.
