# ScoutMatch SNS email subscription guide

## Topic

`ScoutMatchManagementNotificationsAvidan`

## When this is required

**SNS is an optional bonus extension.** The course-facing live demo does not depend on SNS or email delivery. DynamoDB is the source of truth for submitted recommendations.

After four-Lambda `--apply`, `ScoutMatchSubmitPlayerSelectionAvidan` / `SubmitPlayerSelectionToManagement` attempts a sanitized SNS publish only after explicit user confirmation. **SNS publish can succeed even when no email subscription exists**, but **no email will be received** until a subscription is created and confirmed.

Manual email subscription is required only for a live email demo.

## Topic verification

1. Confirm topic `ScoutMatchManagementNotificationsAvidan` exists in **us-east-1** under the same AWS account as ScoutMatch Lambdas.
2. Run `python scripts/configure_sns_lambda_env.py` (configures `ScoutMatchSubmitPlayerSelectionAvidan` only).
3. Re-test Confirm flow. If publish still fails with `NotFoundException`, the topic is missing or in a different account/region.

## Important safety notes

- **No email address is stored in Git.**
- **No hard-coded management email** appears in Lambda code, deploy scripts, or documentation examples.
- The user provides the management email only in the AWS Console during subscription creation.

## Exact manual steps (AWS Console)

1. Open **AWS Console**.
2. Go to **Amazon SNS** → **Topics**.
3. Open topic **`ScoutMatchManagementNotificationsAvidan`**.
4. Click **Create subscription**.
5. **Protocol:** `Email`
6. **Endpoint:** user-provided management email address (entered manually in Console only).
7. Click **Create subscription**.
8. Open the management inbox.
9. Click **Confirm subscription** in the AWS SNS confirmation email.
10. Re-run a confirmed `SubmitPlayerSelectionToManagement` test from the Recruitment Advisor demo.

## Verification after subscription

- SNS topic shows the confirmed email subscription.
- A confirmed player selection publishes a sanitized message (candidate name, role, salary request, budget status, reservation status, approval status).
- Message body contains **no** secrets and **no** subscriber email address.

## If email is not received

| Check | Action |
|-------|--------|
| Subscription pending | Confirm inbox link |
| Wrong topic | Verify `ScoutMatchManagementNotificationsAvidan` |
| Selection not confirmed | User must confirm before write/SNS |
| Budget helper failed | No reservation and no SNS publish |
