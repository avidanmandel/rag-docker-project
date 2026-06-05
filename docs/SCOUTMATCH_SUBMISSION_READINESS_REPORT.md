# ScoutMatch Submission Readiness Report

**Date:** 2026-06-04  
**Branch:** `feature/scoutmatch-agent-flow-extension`  
**Starting commit (SNS pass):** `9fad787`  
**Package status:** **DRAFT** (manual viewport/Console screenshots still required; SNS publish not yet verified live)

---

## Included in repository / draft ZIP

- Application source (Flask, Agent service, four-tool Lambdas, shared football modules)
- Opening-season dataset and knowledge upload scripts
- Tests (437 passed full suite)
- Deployment and validation scripts
- Sanitized documentation set
- Evidence JSON: `artifacts/evidence/scoutmatch_sanitized_aws_evidence.json`

## Excluded (by design)

- `.env`, `.env.agent`, PEM keys, `chat.db`, raw logs
- Complete ARNs, account IDs, Agent IDs in committed docs
- Subscriber email addresses in any committed file
- Unsafe screenshots with private identifiers
- Repair scratch scripts (`fix_agent_model.py`, `repair_agent_runtime.py`) — untracked, not packaged

## Secret scan

**Result:** REVIEW (heuristic matches in code comments / variable names — no live keys committed)  
**Report:** `artifacts/evidence/secret_scan_report.json`  
**Command:** `python scripts/run_secret_scan.py`

## Test result

```
437 passed, 0 failed (python -m pytest -q --cache-clear)
```

## DynamoDB source of truth

- Confirmed player recommendations are persisted in DynamoDB management-review / selection records.
- User-facing status after Confirm: **Pending management approval** (`PENDING_MANAGEMENT_APPROVAL` internally).
- Management approval and signing remain **outside** the application.

## SNS optional extension

| Item | Result |
|------|--------|
| Course-facing live demo depends on SNS | **No** — core workflow is DynamoDB + budget reservation |
| Topic name | `ScoutMatchManagementNotificationsAvidan` |
| Region | `us-east-1` |
| Local discovery | `sts_constructed_fallback` — local IAM lacks `sns:GetTopicAttributes`, `sns:ListTopics`, `sns:CreateTopic`, `sns:Publish` |
| Lambda env configured | **Yes** — `ScoutMatchSubmitPlayerSelectionAvidan` only (`SCOUTMATCH_MANAGEMENT_SNS_TOPIC_ARN`) |
| Lambda publish (live) | **Failed** — `NotFoundException` (topic not found at configured ARN in runtime account/region) |
| Publish only after Confirm | **Verified** (Lambda + unit tests) |
| Deny never publishes | **Verified** |
| Repeat Confirm idempotent (no duplicate SNS) | **Verified** |
| SNS failure non-blocking | **Verified** — DynamoDB write and budget reservation succeed |
| Inbox delivery verified | **No** — email subscription not confirmed in this pass |

## Runtime validation

| Check | Result |
|-------|--------|
| Public health `/api/health` | VERIFIED 200 |
| Four-tool alias validation | VERIFIED BLOCKERS=0 |
| Live rehearsal A–H | VERIFIED BLOCKERS=0 |
| Guardrail live regression | VERIFIED BLOCKERS=0 (v11, alias v22) |
| No-lineup edge case (unit) | VERIFIED — `test_lineup_scoped_to_active_demo_season_only` |
| Clean UI selection wording | VERIFIED — no SNS jargon in ordinary success text |

## Remaining manual artifacts

1. Verify SNS topic exists in **same AWS account and region** as ScoutMatch Lambdas (`us-east-1`)
2. Run `python scripts/configure_sns_lambda_env.py` after topic verification
3. Optional SNS email subscription confirmation (not required for course submission)
4. Viewport screenshots (manual checklist in `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md`)
5. AWS Console evidence screenshots

## ZIP status

**DRAFT** — run `python scripts/prepare_submission_zip.py` after manual screenshots are captured.  
Do **not** mark FINAL until required presentation screenshots are complete. SNS screenshots are optional for course submission.

## Exact next action for the user

1. AWS Console → SNS → confirm topic `ScoutMatchManagementNotificationsAvidan` exists in **us-east-1** under the ScoutMatch account
2. Run `python scripts/configure_sns_lambda_env.py`
3. Re-test Confirm flow; expect optional line **Management notification sent.** only after real publish succeeds
4. Optional: email subscription per `docs/SCOUTMATCH_SNS_EMAIL_SUBSCRIPTION_GUIDE.md`
5. Capture manual viewport and Console screenshots per `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md`
6. Regenerate draft/final ZIP and mark this report **FINAL**
