# ScoutMatch Demo Data Cleanup Audit

Generated: 2026-06-05 14:55 UTC

## Read-only audit result

- DynamoDB table: `ScoutMatchRecruitmentShortlistAvidan`
- PLAYER_SELECTION demo records: **audit_incomplete**
- BUDGET_LEDGER demo records: **audit_incomplete**
- Other football_ops demo records: **audit_incomplete**
- Total demo reserved budget (ledger scan): **audit_incomplete EUR**

## Sanitized record identifiers (sample)

### PLAYER_SELECTION


### BUDGET_LEDGER


## Safe deletion criteria

- Delete only items whose hash key begins with `football_ops#player_selection#` from demo browser tests.
- Delete only items whose hash key begins with `football_ops#budget_ledger#` created by demo selection tests.
- Do not delete baseline club knowledge, production shortlist records, or non-demo lineup records.
- Do not delete SNS topics, Lambdas, Agent versions, or Knowledge Base assets.

## Execution status

- Automatic deletion executed: **no**
- Production records touched: **no**

## Prepared manual cleanup

- Script: `C:/Users/avida/amdocs/lesson 5/Lesson 5-20260517T130502Z-3-001/Lesson 5/Avidan_RAG_Docker_Project/scripts/cleanup_demo_football_ops_records.py`
- Requires explicit confirmation phrase before any operator action.

## Known demo budget side effect

- Prior live browser tests reserved approximately **129,000 EUR** against a **100,000 EUR** cap.
- Live Confirm-path validation should wait until manual cleanup is approved.

## Audit limitation

- Local principal lacked DynamoDB scan permission; counts may be incomplete.
- Re-run `infra/scoutmatch_agent_extension/scripts/audit_demo_data_cleanup.py` from an authorized EC2 or IAM principal before cleanup.

