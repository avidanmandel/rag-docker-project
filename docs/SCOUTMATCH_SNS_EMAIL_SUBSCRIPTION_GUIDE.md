# ScoutMatch SNS email subscription guide

## Topic

`ScoutMatchManagementNotificationsAvidan`

## When this is required

After approved `--apply`, `SubmitPlayerSelectionToManagement` can publish sanitized management notifications to SNS. **SNS publish can succeed even when no email subscription exists**, but **no email will be received** until a subscription is created and confirmed.

Manual email subscription is required for the live email demo.

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
