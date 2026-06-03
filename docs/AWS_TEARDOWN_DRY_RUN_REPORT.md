# AWS Teardown Dry-Run Report — ScoutMatch AI

**Report date:** 2026-06-03 (UTC)  
**Mode:** read-only audit — **no deletions performed**  
**Active release:** `scoutmatch-ai:baseline-club-v14`  
**Lecturer package:** `dist/Avidan_RAG_Docker_Project-lecturer-package-v14.zip`

---

## Summary

This report inventories ScoutMatch AI AWS resources and proposes an ordered teardown plan. Every proposed action is classified. **Do not run destructive steps until the lecturer ZIP is verified and you explicitly approve each phase.**

Classification legend:

| Class | Meaning |
|-------|---------|
| **SAFE_DISPOSABLE** | Validation/demo artifacts; safe to delete after submission approval |
| **REVIEW_REQUIRED** | May be shared, legacy, or needs human confirmation before deletion |
| **DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL** | Core production infrastructure; never auto-delete |

---

## EC2

| Field | Value |
|-------|-------|
| Name tag | `Avidan_amdocs` |
| Instance ID | `i-042cf89f0c8d749f1` |
| Public IP | `3.239.47.249` |
| Private IP | `172.31.15.80` |
| State | `running` |
| Type | `t3.micro` |
| IAM instance profile | `ScoutMatch-EC2-Role` |
| Security group | `sg-007a9218be05fa4f5` (`launch-wizard-49`) |
| Root volume | `vol-04da17740e9484646` (20 GiB, in-use) |

**Proposed action (after approval):** stop Docker container → create final backup if desired → terminate instance → release Elastic IP if allocated.

**Classification:** `DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL`

---

## Docker (on EC2)

| Field | Value |
|-------|-------|
| Container | `scoutmatch-ai` |
| Image | `scoutmatch-ai:baseline-club-v14` |
| State | Up (running) |

**Proposed action (after approval):** `docker stop scoutmatch-ai` then remove container before EC2 termination.

**Classification:** `REVIEW_REQUIRED` (must happen before EC2 termination; not before ZIP approval)

---

## S3 — bucket `oz-bucket-user5`

Application prefix: `scoutmatch/knowledge-base/`

### Production baseline (keep until full teardown approved)

| Prefix | Objects | Notes |
|--------|---------|-------|
| `scoutmatch/knowledge-base/baseline/production/` | 20 | Active production baseline set (10 docs + metadata sidecars) |

**Classification:** `DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL` while production is live; deletable only as part of approved full teardown after EC2 stop.

### Disposable session uploads

| Session ID | Objects | Sample files | Classification |
|------------|---------|--------------|----------------|
| `1b3ca90d78674d3dbcde0d17d9b1c57f` | 2 | `session_b_only_player.txt` | **SAFE_DISPOSABLE** |
| `9b93c2cea44e4fc8ad8f8b2b666eb8c8` | 2 | `session_b_only_player.txt` | **SAFE_DISPOSABLE** |
| `54be3dcc80d64ad0b9982f4c31550ff0` | 2 | `v5_audit.txt` (validation stub) | **SAFE_DISPOSABLE** |
| `32b8db1cc85b41be8578f174b287ba4c` | 22 | business-gate fixture uploads | **SAFE_DISPOSABLE** |

**Proposed action:** delete all four session prefixes recursively, then run one bounded Bedrock sync on `GXN3PZSWRR`.

### Temporary baseline validation folders

Six candidate baseline soak folders under `scoutmatch/knowledge-base/baseline/`:

- `candidate-20260602144524/`
- `candidate-20260602145317/`
- `candidate-20260602145859/`
- `candidate-20260602170702/`
- `candidate-20260602171609/`
- `candidate-soak-20260602215708/`

**Classification:** **SAFE_DISPOSABLE** (deploy/validation artifacts; not the active `production` set)

### Legacy root prefixes (pre-session-scoped uploads)

| Prefix | Objects | Classification |
|--------|---------|----------------|
| `scoutmatch/knowledge-base/player_cvs/` | 10 | **REVIEW_REQUIRED** — old global uploads, superseded by session-scoped model |
| `scoutmatch/knowledge-base/scouting_reports/` | 3 | **REVIEW_REQUIRED** |
| `scoutmatch/knowledge-base/team_requirements/` | 1 | **REVIEW_REQUIRED** |

### Legacy course bucket prefix (non-ScoutMatch data source)

| Prefix | Contents | Classification |
|--------|----------|----------------|
| `data/` | course quick-start files, PNG screenshot, PDFs, txt | **REVIEW_REQUIRED** — indexed by legacy Bedrock DS `J4PVYUXRMR`, not ScoutMatch production |

**Proposed S3 deletions (phase 1, after approval):** session prefixes + candidate baseline folders only.  
**Proposed S3 deletions (phase 2, optional review):** legacy `player_cvs/`, `scouting_reports/`, `team_requirements/`, `data/` objects.

---

## Bedrock

| Field | Value |
|-------|-------|
| Knowledge Base ID | `KOHOL1843O` |
| Name | `knowledge-base-user5` |
| Status | `ACTIVE` |
| Execution role | `AmazonBedrockExecutionRoleForKnowledgeBase_w90im` |

### Attached data sources

| Name | ID | S3 prefix | Role | Classification |
|------|-----|-----------|------|----------------|
| **scoutmatch-player-documents** | `GXN3PZSWRR` | `scoutmatch/knowledge-base/` | **Production ScoutMatch** | `DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL` while course demo active |
| knowledge-base-quick-start-k5idl-data-source | `J4PVYUXRMR` | `data/` | Legacy / shared course quick-start | `REVIEW_REQUIRED` |

Latest production ingestion job: `L1IGBCZUCR` — COMPLETE, 0 failed.

**Proposed actions (after approval):**

1. After S3 session cleanup → one sync on `GXN3PZSWRR` only.
2. Optional: detach/delete legacy DS `J4PVYUXRMR` if `data/` prefix cleanup approved.
3. Delete Knowledge Base `KOHOL1843O` only if course requires full Bedrock teardown — **explicit approval required**.

---

## IAM and network

| Resource | Identifier | Classification |
|----------|------------|----------------|
| EC2 instance profile | `ScoutMatch-EC2-Role` | `DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL` |
| EC2 inline policy | `ScoutMatchAppRuntimePolicy` | `DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL` |
| Bedrock KB execution role | `AmazonBedrockExecutionRoleForKnowledgeBase_w90im` | `DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL` |
| Security group | `sg-007a9218be05fa4f5` (`launch-wizard-49`) | `REVIEW_REQUIRED` — delete only if no other instances use it |

---

## Ordered teardown checklist

1. **Confirm lecturer ZIP** saved locally (`dist/Avidan_RAG_Docker_Project-lecturer-package-v14.zip`).
2. **S3 phase 1 — disposable sessions:** delete four `sessions/<id>/` prefixes → **SAFE_DISPOSABLE**.
3. **S3 phase 1 — disposable baseline candidates:** delete six `baseline/candidate-*` folders → **SAFE_DISPOSABLE**.
4. **Bedrock sync:** one ingestion job on `GXN3PZSWRR`; verify COMPLETE, 0 failed → **REVIEW_REQUIRED**.
5. **S3 phase 2 (optional):** legacy `player_cvs/`, `scouting_reports/`, `team_requirements/` → **REVIEW_REQUIRED**.
6. **S3 phase 2 (optional):** `data/` prefix for legacy DS → **REVIEW_REQUIRED**.
7. **Docker:** stop/remove `scoutmatch-ai` container on EC2 → **REVIEW_REQUIRED**.
8. **EC2:** terminate `i-042cf89f0c8d749f1` → **DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL**.
9. **Bedrock (optional):** detach/delete legacy DS `J4PVYUXRMR` → **REVIEW_REQUIRED**.
10. **Bedrock (optional):** delete KB `KOHOL1843O` → **DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL**.
11. **IAM / SG (optional, last):** remove ScoutMatch-specific roles/policies/security group only after confirming no dependencies → **DO_NOT_DELETE_WITHOUT_EXPLICIT_APPROVAL**.

---

## Reconcile dry-run (production container)

`python scripts/reconcile_session_documents.py --dry-run` completed with no orphan report output beyond `dry_run=True` summary — no blocking reconcile errors observed.

---

## Safety confirmation

- No AWS resources were modified during this audit.
- No S3 objects deleted.
- No EC2, Docker, Bedrock, or IAM changes performed.
- No cleanup `--apply` executed.
