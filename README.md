# ScoutMatch AI

**AI-Powered Football Recruitment Assistant**

ScoutMatch AI helps football club managers, coaches, and scouts find the right players for their squad. Upload player CVs and scouting reports, then ask natural-language questions in Hebrew or English. The assistant retrieves evidence from **Amazon Bedrock Knowledge Base**, compares candidates, and explains recommendations — grounded strictly in uploaded documents.

---

## Project topic and document set

**Topic:** AI-powered football recruitment assistant with strict session-scoped RAG.

**Chosen document set (demo / sample):**

| Category | Location | Examples |
|----------|----------|----------|
| Player CVs | `sample_scout_data/player_cvs/` | TXT, CSV, PDF, DOCX formats |
| Scouting reports | `sample_scout_data/scouting_reports/` | Per-player reports |
| Team requirements | `sample_scout_data/team_requirements.txt` | Squad needs |
| Live demo upload | `sample_scout_data/demo_upload_later/` | Optional extra CV |

Production stores uploaded session documents under `s3://<bucket>/scoutmatch/knowledge-base/sessions/<session_id>/`.

---

## Public test URL

**Live deployment:** http://3.239.47.249/

Verify:

- http://3.239.47.249/api/health
- http://3.239.47.249/api/status → `ready: true`, `rag_backend: aws_kb`

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

Live demo upload: `sample_scout_data/demo_upload_later/goalkeeper_marco_silva.txt` (includes neutral `COMPACT FACT PROFILE SUMMARY` like other goalkeeper CVs; no predetermined recommendation language)

See `SCOUTMATCH_DEMO_QUESTIONS.md` and `SCOUTMATCH_MANUAL_TESTS.md`.

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

See `EC2_DEPLOYMENT_GUIDE.md` for full deployment steps.

---

## Testing

```powershell
python tests/test_scoutmatch.py
python test_aws_kb.py   # live AWS only, requires credentials
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

Set `RAG_BACKEND=local` with `GEMINI_API_KEY` and `HF_TOKEN` to use the original FAISS pipeline over `data/`. Course starter files remain for local testing only.

---

## Screenshots

Submission evidence lives in `submission_evidence/`:

- **Automated:** API JSON snapshots, endpoint results, QA summary (see `submission_evidence/README.md`)
- **Manual browser:** `submission_evidence/MANUAL_BROWSER_SCREENSHOT_CHECKLIST.md` — home page, grounded answers, refusals, delete/clear confirmations
- **AWS Console:** `submission_evidence/AWS_CONSOLE_SCREENSHOT_CHECKLIST.md` — Bedrock KB, data source, sync, EC2, security group

Capture PNGs before final ZIP upload. Do not commit secrets in screenshots.

---

## Cleanup (after screenshots and demo)

**Run only after** you have captured all required screenshots and finished the live demo.

1. Delete disposable test sessions in the UI (or API with `delete_documents: true`).
2. On EC2, run **dry-run first** (no deletions):

   ```bash
   bash scripts/aws_cleanup_dry_run.sh
   ```

3. Do **not** delete the Bedrock Knowledge Base, EC2 instance, or production runtime DB unless your course explicitly requires teardown.
4. See `docs/SUBMISSION_CHECKLIST.md` and `docs/DEPLOYMENT_RUNBOOK.md`.

---

## Known limitations

See `docs/KNOWN_LIMITATIONS.md` — Bedrock ingestion latency, stale historical answers, session-scoped retrieval only, single-host deployment.

---

## Further documentation

| Doc | Purpose |
|-----|---------|
| `docs/PROJECT_STATE.md` | Release commit, image tag, URL |
| `docs/FINAL_QA_REPORT.md` | QA verdict and strict validation |
| `docs/BUSINESS_ACCEPTANCE_MATRIX.md` | Business-logic acceptance gate (v11) |
| `docs/DEPLOYMENT_RUNBOOK.md` | EC2 deploy and rollback |
| `AGENTS.md` | Agent/developer guide |
| `docs/AGENT_HANDOFF.md` | Handoff notes |
