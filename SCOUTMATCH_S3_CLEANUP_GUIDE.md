# ScoutMatch S3 Cleanup Guide

Use this guide **manually** before the final demo. Do not run destructive AWS commands from automated scripts unless you intend to.

## Why cleanup is needed

The ScoutMatch knowledge-base prefix (`scoutmatch/knowledge-base/`) may still contain **temporary test uploads** from earlier sessions — including biased Marco Silva text such as:

> Should rank as TOP RECOMMENDATION once uploaded to ScoutMatch system

Local files in `sample_scout_data/` have been cleaned, but **S3 and the Bedrock Knowledge Base index only update after you remove old objects and re-sync**.

---

## Step 1 — List current ScoutMatch objects only

Using AWS CLI (replace bucket name with your configured bucket):

```powershell
aws s3 ls s3://YOUR_BUCKET/scoutmatch/knowledge-base/ --recursive
```

Review the list. Objects under `scoutmatch/knowledge-base/` are ScoutMatch demo files.  
**Do not delete** objects outside this prefix.

Typical structure:

```
scoutmatch/knowledge-base/team_requirements.txt
scoutmatch/knowledge-base/player_cvs/...
scoutmatch/knowledge-base/scouting_reports/...
scoutmatch/knowledge-base/demo_upload_later/...   (if uploaded)
```

---

## Step 2 — Remove only temporary ScoutMatch test files

Delete **everything under** `scoutmatch/knowledge-base/`:

```powershell
aws s3 rm s3://YOUR_BUCKET/scoutmatch/knowledge-base/ --recursive
```

This removes ScoutMatch demo uploads only when your bucket uses the configured prefix.  
Verify no unrelated prefixes were included before confirming.

**Alternative (selective):** delete individual keys shown in Step 1 if you prefer a manual review.

---

## Step 3 — Sync the empty data source

After S3 cleanup, trigger one ingestion sync so Bedrock re-indexes:

1. Open ScoutMatch AI in the browser, **or**
2. Call `POST /api/ingestion/sync` (if configured in your deployment)

Wait until ingestion status is **COMPLETE** before uploading new files.

---

## Step 4 — Upload the clean initial demo set

Upload these files **through the website** (or CLI to the same prefix), one batch or individually, waiting for sync after each upload if your demo requires it:

| File | Purpose |
|------|---------|
| `sample_scout_data/team_requirements.txt` | Squad recruitment brief |
| `sample_scout_data/player_cvs/goalkeeper_daniel_cohen.txt` | Initial GK CV |
| `sample_scout_data/scouting_reports/goalkeeper_daniel_cohen_report.txt` | Daniel Cohen report |
| `sample_scout_data/player_cvs/goalkeeper_yossi_levi.txt` | Initial GK CV |
| `sample_scout_data/scouting_reports/goalkeeper_yossi_levi_report.txt` | Yossi Levi report |
| `sample_scout_data/player_cvs/goalkeeper_omer_azulay.txt` | Initial GK CV |
| `sample_scout_data/scouting_reports/goalkeeper_omer_azulay_report.txt` | Omer Azulay report |

**Do not upload Marco Silva yet.**

---

## Step 5 — Verify initial demo

Ask the Hebrew goalkeeper recruitment question (see `SCOUTMATCH_MANUAL_TESTS.md`).  
Confirm explicit player name, valid reasoning, Hebrew response, and readable sources.

---

## Step 6 — Late live-demo upload only

After the initial demo sequence, upload **only**:

```
sample_scout_data/demo_upload_later/goalkeeper_marco_silva.txt
```

Wait for ingestion **COMPLETE**, then re-ask the same recruitment question.  
Marco Silva should appear or expand the recommendation based on the new neutral CV (7 years experience, relocation north, build-up profile).

---

## What to preserve

- Files **outside** `scoutmatch/knowledge-base/` in the same bucket (if any) — leave untouched
- Local `sample_scout_data/` — source of truth for re-uploads
- `.env` and AWS resource configuration — do not modify as part of cleanup

---

## CLI upload example (optional)

If uploading via CLI instead of the website, mirror the app's key layout:

```powershell
aws s3 cp sample_scout_data/team_requirements.txt s3://YOUR_BUCKET/scoutmatch/knowledge-base/team_requirements.txt
aws s3 cp sample_scout_data/player_cvs/goalkeeper_daniel_cohen.txt s3://YOUR_BUCKET/scoutmatch/knowledge-base/player_cvs/goalkeeper_daniel_cohen.txt
# ... repeat for each initial-demo file
```

Then run one sync and wait for COMPLETE.

---

## Checklist

- [ ] Listed objects under `scoutmatch/knowledge-base/` only
- [ ] Removed temporary test files from that prefix
- [ ] Ran one sync; status COMPLETE
- [ ] Uploaded clean initial goalkeeper dataset (no Marco Silva)
- [ ] Verified Hebrew recruitment Q&A
- [ ] Uploaded Marco Silva only for late demo
- [ ] Re-verified recommendation after Marco upload
