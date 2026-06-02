# Agent Handoff — ScoutMatch AI

Last updated: 2026-06-02

## Current state

| Item | Value |
|------|-------|
| Branch | `feature/session-scoped-documents` |
| Target image | `scoutmatch-ai:session-docs-v10` |
| Rollback | `scoutmatch-ai:session-docs-v9` |
| EC2 | `ubuntu@3.239.47.249` |
| Release checkout | `/home/ubuntu/scoutmatch-ai-session-docs-release` |

## What was fixed (v10)

1. **Amit Levy CSV aggregates** — All deterministic aggregates (relocation, defenders, availability) now prefer upload-time `session_player_facts` from SQLite, not only chunk extraction. Added `parsed_position` at upload for CSV/PDF/DOCX/TXT.
2. **Audit runner** — Session IDs read from `${LOG_FILE}` (last line); persistence uses tolerant HTTP checks; fallback to SESSION_A if SESSION_B unavailable.
3. **Deploy reliability** — Validation exit code gates cutover; LF enforced for shell scripts.

## Strict validation

Run on EC2 before any cutover:

```bash
bash scripts/run_strict_release_audit_v10.sh
grep '^BLOCKERS ' /tmp/strict_release_audit_v10.log
```

Must show `BLOCKERS 0` for production cutover via `deploy_session_docs_v10.sh`.

## Known gaps (pre-v10 audit)

v9 strict audit failed on Amit Levy in relocation/defender answers. v10 code addresses root cause (registry facts + position). Re-verify on EC2 after build.

## Submission

- Checklist: `docs/SUBMISSION_CHECKLIST.md`
- ZIP script: `bash scripts/prepare_submission_zip.sh` → `dist/Avidan_RAG_Docker_Project-submission.zip`
- AWS cleanup (dry-run only): `bash scripts/aws_cleanup_dry_run.sh`

## Do not

- Print or commit secrets (`.env`, PEM, DB contents)
- Delete production user data or Bedrock KB
- Cut over with `BLOCKERS > 0`
- Leave loopback candidate containers on port 5001 after validation

## Next agent actions

1. Push latest commit to origin.
2. On EC2: `git pull`, `bash scripts/run_strict_release_audit_v10.sh`.
3. If `BLOCKERS 0`: `bash scripts/deploy_session_docs_v10.sh`.
4. Update `docs/PROJECT_STATE.md` and `docs/FINAL_QA_REPORT.md` with v10 image ID and audit result.
