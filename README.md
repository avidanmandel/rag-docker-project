# ScoutMatch AI

**AI-Powered Football Recruitment Assistant**

ScoutMatch AI is an **opening-season scouting workspace** for **Scouts / Recruitment Analysts / Professional Assistants**. Every new conversation starts with 15 current club players, 8 pre-scouted recruitment candidates, and preloaded club knowledge. Upload additional CVs per session, compare candidates, respond to coach briefs, and prepare grounded recommendations for management and proposed lineups for head-coach review.

---

## Project topic

**Chosen topic:** Football recruitment assistant based on uploaded player CVs, scouting reports, and club documents.

## Main project flow

```
Documents
    → Amazon S3
    → Amazon Bedrock Knowledge Base
    → Flask application (boto3)
    → Docker container
    → Amazon EC2
    → public browser access
```

## Final hardening pass (2026-06-04)

| Item | Status |
|------|--------|
| Full pytest | `475 passed` (`python -m pytest -q`) |
| Business workflow v2 (feature-flagged) | See `docs/SCOUTMATCH_BUSINESS_WORKFLOW_V2.md` |
| Public four-tool validation | `BLOCKERS=0` |
| Guardrail live regression | `BLOCKERS=0` (v11, alias v22) |
| Live rehearsal script | `python scripts/final_hardening_live_rehearsal.py` |
| SNS management notification | **Optional future extension** — not required for course demo or submission |
| Course readiness audit | `docs/SCOUTMATCH_FINAL_COURSE_READINESS_REPORT.md` |
| Submission package | **READY_FOR_MANUAL_SCREENSHOTS** — see `docs/SCOUTMATCH_SUBMISSION_READINESS_REPORT.md` |

## Current production release

| Item | Value |
|------|-------|
| Docker image (production target) | `scoutmatch-ai:agent-extension-v15` |
| Rollback image | `scoutmatch-ai:baseline-club-v14` |
| Public test URL | http://3.239.47.249/ |
| Diagnostic route | http://3.239.47.249/recruitment-advisor |
| Production container | `scoutmatch-ai` |

Verify:

- http://3.239.47.249/api/health
- http://3.239.47.249/api/status → `ready: true`, `agent_extension_enabled: true`, `chat_backend: bedrock_agent`
- Root polished UI at `/` is the main presentation interface; `/recruitment-advisor` remains for debugging only.

## Main features

- Grounded answers from uploaded documents only (strict RAG)
- Source attribution cards for every grounded answer
- Read-only baseline club documents (budget, tactics, squad depth, fixtures)
- Session-scoped candidate uploads (each conversation has its own document set)
- Supported upload formats: **TXT, PDF, DOCX, CSV** (plus MD, HTML, DOC, XLS, XLSX)
- English and Hebrew questions
- Delete single uploaded document (with stale-answer protection)
- **CLEAR DOCUMENTS** (removes all session uploads)
- Safe refusal for unsupported or out-of-scope questions

---

## Documents used

### Baseline club documents (read-only, production)

Ten managed files under `sample_scout_data/baseline/` seed the production baseline set (club profile, tactical model, squad depth chart, transfer budget, fixtures, recruitment priorities, policy, DOCX summary, PDF overview). These are indexed once in S3 under `scoutmatch/knowledge-base/baseline/production/` and available in every session without upload.

### Candidate demo documents (session upload examples)

| Category | Location | Purpose |
|----------|----------|---------|
| Player CVs | `sample_scout_data/player_cvs/` | TXT and CSV format examples |
| Scouting reports | `sample_scout_data/scouting_reports/` | Per-player narrative reports |
| Demo candidates | `sample_scout_data/demo_candidates/` | PDF, DOCX, CSV upload demos (Eyal Mor, Ron Ben Ari, Tal Raz, etc.) |
| Team requirements | `sample_scout_data/team_requirements.txt` | Squad needs reference |
| Live demo upload | `sample_scout_data/demo_upload_later/` | Optional extra CV for presentations |

Production session uploads are stored under `s3://<bucket>/scoutmatch/knowledge-base/sessions/<session_id>/`.

---

## Supported upload formats

TXT, PDF, DOCX, CSV (also MD, HTML, DOC, XLS, XLSX per `config.py`).

---

## Example grounded questions

After uploading player CVs in a session:

| Language | Example question |
|----------|------------------|
| English | Who is Or David? |
| English | Show all candidates willing to relocate |
| English | What is the total annual salary of all uploaded players? |
| English | Compare all defenders |
| Hebrew | מי זה אור דוד? |
| Hebrew | מהי המשכורת הכוללת של כל השחקנים? |

Out-of-domain (should refuse, no sources): *Are there good players on the Titanic?*

---

## Architecture (production)

```
Documents (upload)
    → Amazon S3 (scoutmatch/knowledge-base/sessions/<session_id>/)
    → Bedrock Knowledge Base ingestion (sync)
    → Bedrock retrieve + Converse generation
    → Flask app (boto3) in Docker
    → EC2 (port 80)
    → Public browser access
```

```
Browser (phone / laptop)
    → EC2 public IP (port 80)
    → Docker container
    → Flask (0.0.0.0:5000)
    → boto3
    → Amazon S3 (scoutmatch/knowledge-base/)
    → Bedrock Knowledge Base ingestion
    → Bedrock Knowledge Base retrieve()
    → validate ScoutMatch S3 sources
    → build grounded context
    → Bedrock generation model (Converse API)
    → Grounded answer with validated source cards
```

ScoutMatch uses an **explicit retrieve-then-generate** pipeline (not `retrieve_and_generate` citations) because Bedrock can return citation shells without usable `retrievedReferences`. Source cards always come from validated Knowledge Base retrieval results under the configured ScoutMatch S3 prefix.

**Architecture:**
```
Bedrock KB retrieve → ScoutMatch prefix validation → complete diverse context selection
→ deterministic verified requirement matrix → Bedrock Converse explanation
→ contradiction validation → ScoutMatch-only source cards
```

The AI explains retrieved evidence in natural language. **Backend code** verifies mandatory numeric and relocation constraints in a deterministic matrix. The model must not redo arithmetic or override PASS / FAIL / UNKNOWN statuses from the verified matrix.

**Quality guards:**
- **Out-of-domain refusal** — unrelated questions (e.g. politics, geography) are refused before retrieval; no random football sources attached.
- **Follow-up handling** — short follow-up questions (e.g. salary, relocation) are allowed when recent chat history contains football-player context.
- **Diverse but complete source selection** — comparison/recommendation queries deduplicate by filename, prefer coverage across multiple player CVs, scouting reports, and team requirements, and may include up to `AWS_KB_MAX_CHUNKS_PER_SOURCE` useful chunks per file when they add distinct facts.
- **Single name retry** — if a grounded recommendation fails validation only because no full player name appears, Bedrock generation retries once with a stricter instruction; strict refusal remains if the retry still omits a name.
- **No general-knowledge fallback** — answers come only from retrieved ScoutMatch context.

| Component | Role |
|-----------|------|
| `app.py` | Flask routes: chat, upload, ingestion status |
| `aws_kb_engine.py` | Bedrock KB retrieve, ScoutMatch source filter, explicit generation, strict RAG |
| `aws_storage_service.py` | S3 upload, document listing, KB sync |
| `database.py` | SQLite chat history + Bedrock session IDs |
| `rag_engine.py` | Local FAISS mode (development fallback) |
| `templates/`, `static/` | ScoutMatch UI |

---

## Modes

| Mode | `RAG_BACKEND` | Use case |
|------|---------------|----------|
| **Production** | `aws_kb` | EC2 + S3 + Bedrock Knowledge Base |
| **Development** | `local` | FAISS + Gemini + Hugging Face (optional) |

Production mode does **not** use local FAISS or course documents as the main path.

---

## Environment variables

Copy `.env.example` to `.env` locally (**never commit `.env`**):

```powershell
copy .env.example .env
```

| Variable | Required (AWS) | Description |
|----------|----------------|-------------|
| `RAG_BACKEND` | Yes | `aws_kb` for production |
| `AWS_REGION` | Yes | e.g. `us-east-1` |
| `BEDROCK_KB_ID` | Yes | Knowledge Base ID |
| `BEDROCK_DATA_SOURCE_ID` | Yes | Data source ID (must point to ScoutMatch S3 prefix) |
| `BEDROCK_MODEL_ARN` | Yes | Bedrock foundation model ARN |
| `AWS_S3_BUCKET` | Yes | S3 bucket name |
| `AWS_S3_PREFIX` | Yes | Default: `scoutmatch/knowledge-base/` |
| `AWS_KB_TOP_K` | No | Validated ScoutMatch chunks used for generation (default 5) |
| `AWS_KB_RETRIEVE_CANDIDATES` | No | Raw KB retrieve count before ScoutMatch filtering (default 30) |
| `AWS_KB_CONTEXT_SOURCE_LIMIT` | No | Max unique source files in comparison context (default 10) |
| `AWS_KB_MAX_CHUNKS_PER_SOURCE` | No | Max useful chunks per source file in comparison context (default 2) |
| `AWS_KB_CONTEXT_EXCERPT_MAX` | No | Max characters per chunk in grounded context (default 1200) |
| `AWS_KB_MIN_SCORE` | No | Minimum relevance score (optional) |
| `MAX_UPLOAD_MB` | No | Upload limit (default 25) |
| `FLASK_HOST` | No | Default `0.0.0.0` |
| `FLASK_PORT` | No | Default `5000` |

For local development only: `GEMINI_API_KEY`, `HF_TOKEN`.

---

## S3 prefix requirement

All ScoutMatch documents must live under:

```
s3://<bucket>/scoutmatch/knowledge-base/
```

Example layout:

```
scoutmatch/knowledge-base/player_cvs/goalkeeper_daniel_cohen.txt
scoutmatch/knowledge-base/scouting_reports/goalkeeper_daniel_cohen_report.txt
scoutmatch/knowledge-base/team_requirements/team_requirements.txt
```

**Important:** Configure your Bedrock data source to index this prefix. If your KB currently indexes unrelated course documents, create a new data source restricted to `scoutmatch/knowledge-base/` in the AWS Console. Do not delete existing AWS data automatically.

---

## Upload and sync flow

1. User clicks **Upload CV** in the sidebar
2. Flask validates file type and size
3. File uploads to S3 under the ScoutMatch prefix
4. Flask starts a Bedrock Knowledge Base ingestion job
5. UI polls `/api/ingestion/status` until `COMPLETE`
6. User asks questions about the newly indexed player

**Sidebar display deduplication:** Re-uploading a CV with the same logical name creates timestamped S3 keys (for example `goalkeeper_daniel_cohen_20260531_183000.txt`). All raw objects remain in S3 and in the Knowledge Base. `GET /api/documents` returns a deduplicated display list for the sidebar plus `raw_object_count` for diagnostics. Scouting reports (`*_report.txt`) are never collapsed into player CVs.

Supported types: `.txt`, `.md`, `.html`, `.pdf`, `.doc`, `.docx`, `.csv`, `.xls`, `.xlsx`

---

## Strict RAG behaviour

ScoutMatch answers **only** from uploaded player and team documents.

- Unrelated questions (e.g. "Who is Donald Trump?") receive a strict refusal
- Recommendations cite document evidence
- When multiple candidates satisfy all mandatory requirements, the answer acknowledges each exact-match candidate before stating a preference or uncertainty
- **Exact-match acknowledgment validation** rejects answers that omit an exact-match candidate or describe a verified PASS field as missing, unknown, insufficient, or failed
- **Fact parsing** prefers structured CV fields (`Build-up Ability:`, `Calmness Under Pressure:`); a narrow narrative fallback maps clearly positive football phrases to `Strong` only when structured values are missing; ambiguous text remains **UNKNOWN**
- **Bounded retries:** one matrix-contradiction retry, one exact-match acknowledgment retry, and one name retry maximum per answer; if exact-match validation still fails, a **deterministic matrix-backed fallback** is returned (never general-knowledge)
- **Main source** in the UI follows the recommended or directly referenced player's CV (or scouting report if no CV), not merely the highest retrieval score; all validated sources remain under **Retrieved evidence**
- No general-knowledge fallback in AWS mode

Refusal messages:
- **EN:** *I do not have enough information in the uploaded player and team documents…*
- **HE:** *אין לי מספיק מידע במסמכי השחקנים ובמסמכי הקבוצה…*

---

## Sample demo data

Synthetic demo files are in `sample_scout_data/` (not auto-uploaded to AWS):

```powershell
# Upload manually during demo prep:
# sample_scout_data/team_requirements.txt
# sample_scout_data/player_cvs/*.txt
# sample_scout_data/scouting_reports/*.txt
```

Live demo upload: `sample_scout_data/demo_upload_later/goalkeeper_marco_silva.txt` (optional extra CV for presentations)

Included format examples in this package: TXT (`forward_or_david.txt`), PDF (`ron_ben_ari_cv.pdf`), DOCX (`dor_levi_cv.docx`), CSV (`eyal_mor_cv.csv`).

---

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env — set RAG_BACKEND=aws_kb and AWS values
python app.py
```

Open http://127.0.0.1:5000

Verify:
- http://127.0.0.1:5000/api/health
- http://127.0.0.1:5000/api/status

---

## Docker

```powershell
docker build -t scoutmatch-ai .
docker run --rm --env-file .env -p 5000:5000 --name scoutmatch scoutmatch-ai
```

For EC2 global access, map host port 80 → container 5000:

```bash
docker run -d --name scoutmatch --restart unless-stopped \
  -p 80:5000 --env-file .env scoutmatch-ai
```

See `docs/DEPLOYMENT_RUNBOOK.md` for EC2 production layout and health checks.

---

## Testing

```powershell
python -m pytest tests/test_scoutmatch.py tests/test_baseline_club_knowledge.py -q --tb=no
```

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | ScoutMatch UI |
| GET | `/api/health` | Flask health |
| GET | `/api/status` | Engine + AWS status |
| GET | `/api/documents` | List S3 documents for sidebar (deduplicated display + `raw_object_count` in AWS mode) |
| POST | `/api/documents/upload` | Upload to S3 + start ingestion |
| GET | `/api/ingestion/status` | Ingestion job status |
| POST | `/api/sessions` | New chat (does not reset S3) |
| POST | `/api/sessions/<id>/messages` | Ask ScoutMatch AI |

---

## Security

- Never commit `.env`, AWS keys, or API tokens
- Use EC2 IAM role in production (no keys in Docker image)
- Reset Project is disabled in AWS mode
- No public S3 delete endpoints

---

## Local development fallback

Production ScoutMatch uses **AWS Knowledge Base** with the `scoutmatch/knowledge-base/` S3 prefix and `sample_scout_data/` as the repository source-data reference. The legacy `data/` course files (Flask lectures, docker PDF, risk report, and other unrelated starter documents) were removed and are **not** part of the final submission.

Optional local FAISS mode (`RAG_BACKEND=local` with `GEMINI_API_KEY` and `HF_TOKEN`) may create or use a local `data/` directory at runtime for developer uploads only. This path is **not** the production deployment.

---

## Screenshots

Final submission screenshots are in **`submission_evidence/final_v14/`** (11 PNG files).

| File | What it proves |
|------|----------------|
| `01_bedrock_knowledge_base.png` | Bedrock Knowledge Base exists and the ScoutMatch data source is attached |
| `02_bedrock_data_source_sync_complete.png` | Active data source AVAILABLE; latest sync COMPLETE; failed files 0; warnings 0 |
| `03_ec2_instance_running.png` | Production EC2 instance running |
| `04_docker_container_running.png` | Container `scoutmatch-ai` on `baseline-club-v14`, port 80→5000 |
| `05_public_scoutmatch_homepage.png` | Public homepage loads |
| `06_grounded_budget_answer_with_sources.png` | Grounded aggregate answer with source cards |
| `07_grounded_refusal_for_out_of_scope_questions.png` | Strict refusal with no sources |
| `08_uploaded_candidate_answer_with_source.png` | Session-scoped answer from uploaded candidate |
| `09_deleted_candidate_refusal.png` | After document delete, stale facts are refused |
| `10a_before_clear_documents_two_files.png` | Two session documents visible before clear |
| `10b_after_clear_documents_refusal.png` | After clear documents, session questions refused |

See `submission_evidence/README.md` for the full proof table.

---

## Cleanup (after ZIP review — pending user approval)

**AWS resources have not been deleted.** Final AWS teardown must run **only after** the submission ZIP is reviewed and you explicitly approve cleanup.

**Deleted AWS resources after completion:** none yet (EC2, Bedrock KB, and S3 project prefixes remain active pending post-submission approval).

### Pending teardown checklist

- [ ] EC2 instance hosting ScoutMatch AI (`3.239.47.249`)
- [ ] Disposable S3 session objects under `scoutmatch/knowledge-base/sessions/`
- [ ] Temporary demo uploads created during validation
- [ ] Optional temporary Bedrock resources (legacy data source on `data/` prefix) — only if approved and no longer needed
- [ ] Optional unused IAM resources — only if approved and no longer needed

Before any destructive step:

1. Confirm the lecturer package ZIP is saved locally.
2. Review `docs/SUBMISSION_CHECKLIST.md` and approve teardown phases explicitly.
3. Do **not** delete the Bedrock Knowledge Base, EC2, or production runtime DB without explicit approval.

See `docs/SUBMISSION_CHECKLIST.md` and `docs/DEPLOYMENT_RUNBOOK.md`.

---

## Optional ScoutMatch Bedrock Agent and Flow Extension

ScoutMatch AI **opening-season workspace** uses the Bedrock Agent path on the polished root UI. **v14 production RAG rollback** remains available. (same Flask session chat, EC2 Docker image, S3 baseline, and Knowledge Base).

This repository adds an **optional**, isolated Bedrock extension under `infra/scoutmatch_agent_extension/`:

- **Agent:** `scoutmatch-recruitment-agent-user5-avidan` with four Action Groups and four deterministic Lambdas
- **Guardrail:** `scoutmatch-guardrail-user5-avidan` (agent-only; no account-level enforcement)
- **Flow:** `scoutmatch-recruitment-flow-user5-avidan` (Input → Agent alias → Output)
- **Optional Flask route:** `POST /api/recruitment-flow/chat` (disabled by default via `.env.agent.example`)

Local tests:

```bash
python -m pytest infra/scoutmatch_agent_extension/tests -q
```

Safe deploy (plan is default):

```bash
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --plan
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --apply
```

Documentation: `docs/SCOUTMATCH_AGENT_EXTENSION.md`, `docs/SCOUTMATCH_FLOW_EXTENSION.md`, `docs/SCOUTMATCH_AGENT_REQUIREMENTS_MATRIX.md`.  
Screenshots: `infra/scoutmatch_agent_extension/evidence/SCREENSHOT_CHECKLIST.md`.  
Production EC2 was **not** modified by this extension.

### Course compliance audit

- Matrix: `docs/COURSE_REQUIREMENTS_COMPLIANCE_MATRIX.md`
- Demo script: `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md`
- Screenshot guide: `docs/SCOUTMATCH_DYNAMIC_SCREENSHOT_GUIDE.md`
- Presentation outline: `docs/SCOUTMATCH_PRESENTATION_CONTENT.md`
- Submission ZIP: `docs/SUBMISSION_CHECKLIST.md`

### Final four-Lambda Recruitment Advisor (applied — branch `feature/scoutmatch-agent-flow-extension`)

Sporting-director squad planning through **one Bedrock Agent**, **one central Guardrail**, **one Knowledge Base association (ENABLED)**, and **exactly four user-facing Tools** — each with its own Action Group and dedicated Lambda:

| Tool | Action Group | Lambda |
|------|--------------|--------|
| `PlanMatchTactics` | `ScoutMatchTacticsActionsAvidan` | `ScoutMatchPlanMatchTacticsAvidan` |
| `SubmitPlayerSelectionToManagement` | `ScoutMatchSelectionAgAvidan` | `ScoutMatchSubmitPlayerSelectionAvidan` |
| `FinalizeCurrentLineup` | `ScoutMatchLineupActionsAvidan` | `ScoutMatchFinalizeCurrentLineupAvidan` |
| `GenerateCurrentLineupBoard` | `ScoutMatchLineupBoardActionsAvidan` | `ScoutMatchGenerateLineupBoardAvidan` |

- **Static evidence:** Bedrock Knowledge Base (`knowledge-base-user5`) — club policies, CVs, scouting reports, tactical documents under `scoutmatch/knowledge-base/tactical/`
- **Dynamic state:** DynamoDB operational records (`ScoutMatchFootballOperationsAvidan` or approved fallback prefix on shortlist table)
- **Management alerts:** SNS topic `ScoutMatchManagementNotificationsAvidan` (manual email subscription required — see `docs/SCOUTMATCH_SNS_EMAIL_SUBSCRIPTION_GUIDE.md`)
- **Lineup boards:** private SVG under `scoutmatch/football-operations/lineups/`, served via `GET /api/recruitment-advisor/lineups/<lineup_id>/image`
- **Legacy resources preserved** but detached from the Agent (native router, old football groups, shortlist/workflow Lambdas — not deleted)

Deploy and validate:

```bash
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --plan
python infra/scoutmatch_agent_extension/scripts/deploy_scoutmatch_extension.py --apply
python infra/scoutmatch_agent_extension/scripts/validate_four_lambda_final.py
```

Optional UI (disabled by default locally; enable with `SCOUTMATCH_AGENT_EXTENSION_ENABLED=true` in `.env.agent` — never commit):

- `/recruitment-advisor`
- `POST /api/recruitment-advisor/chat` via `boto3.client("bedrock-agent-runtime").invoke_agent(...)`

**Production EC2:** stable v14 remains on `scoutmatch-ai:baseline-club-v14` until safe cutover. See `scripts/deploy_recruitment_advisor_ec2.sh` for candidate-port validation and rollback to v14.

---

## Known limitations

See `docs/KNOWN_LIMITATIONS.md` — Bedrock ingestion latency, stale historical answers, session-scoped retrieval only, single-host deployment.

---

## Further documentation

| Doc | Purpose |
|-----|---------|
| `docs/PROJECT_STATE.md` | Release commit, image tag, public URL |
| `docs/FINAL_QA_REPORT.md` | QA verdict and strict validation |
| `docs/DEPLOYMENT_RUNBOOK.md` | EC2 production layout, health checks, rollback |
| `docs/KNOWN_LIMITATIONS.md` | Verified limitations (baseline + session scopes) |
| `docs/RAG_DATA_LIFECYCLE.md` | Upload, sync, delete, and clear lifecycle |
| `docs/SUBMISSION_CHECKLIST.md` | Pre-submit verification checklist |
| `submission_evidence/README.md` | Final screenshot proof table |
