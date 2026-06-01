# ScoutMatch AI — Manual Test Plan

Step-by-step verification before demo or EC2 deployment.

---

## Test A — UI branding

Production AWS mode uses an explicit retrieve-then-generate pipeline: Bedrock KB `retrieve()` → ScoutMatch S3 prefix validation → complete diverse context selection → **deterministic verified requirement matrix** → Bedrock Converse → matrix contradiction validation → source cards.

**Quality checks:**
- Backend code verifies numeric constraints (experience, salary, relocation) — the model must not contradict the verified matrix.
- Unrelated questions (e.g. `מי זה דונלד טראמפ?`, `What is the capital of New Zealand?`) must return the exact strict refusal with **no sources**.
- Follow-up questions (e.g. `ומה השכר שלו?`) must work only when prior chat contains football-player context.
- Comparison questions must include multiple unique goalkeeper CV files in sources when available (Daniel Cohen, Yossi Levi, Omer Azulay).
- Short recommendation questions (e.g. `מי השוער המתאים ביותר למשחק רגל?`) should name a player explicitly; one safe generation retry is allowed before strict refusal.
- Context selection may include up to two distinct chunks per CV/report when they add different facts.
- No `knowledge_test.txt` or old course files in sources.

1. Open http://127.0.0.1:5000 (or EC2 public IP)
2. Confirm title **ScoutMatch AI**
3. Confirm subtitle / empty state: *Find the right player for your squad*
4. Confirm badges: **AWS Bedrock KB connected** (AWS mode), **Grounded answers only**
5. Confirm **Upload CV** button visible

**Pass:** Professional football scouting UI, responsive on mobile width

---

## Test B — Upload team requirements

1. Upload `sample_scout_data/team_requirements.txt`
2. Confirm message: uploading to S3
3. Confirm sync status appears

**Pass:** File accepted, no validation error

---

## Test C — Upload goalkeeper CVs

Upload:
- `sample_scout_data/player_cvs/goalkeeper_daniel_cohen.txt`
- `sample_scout_data/player_cvs/goalkeeper_yossi_levi.txt`
- `sample_scout_data/player_cvs/goalkeeper_omer_azulay.txt`

**Pass:** All three upload successfully

---

## Test D — Wait for KB sync

1. Poll sidebar sync status or `GET /api/ingestion/status`
2. Wait until status = **COMPLETE**

**Pass:** UI shows "Knowledge base updated"

---

## Test E — Grounded recruitment question

Ask (Hebrew):
```
אני מחפש שוער עם ניסיון, רגוע תחת לחץ וטוב במשחק רגל. מי מתאים?
```

**Pass:** Grounded answer recommending a goalkeeper with document evidence

---

## Test F — Source display

1. Expand **Retrieved evidence** under the answer
2. Confirm **Main source** filename visible — for recommendations it should match the preferred player's CV when available (not necessarily the highest score chunk)
3. Confirm all supporting source cards remain listed under **Retrieved evidence**
4. Confirm score and text excerpt shown

**Pass:** Sources match uploaded CV filenames; Main source aligns with recommended or directly referenced player

---

## Test F2 — Sidebar document deduplication

1. Call `GET /api/documents` (or inspect sidebar after duplicate CV uploads)
2. Compare `raw_object_count` with the length of the `documents` array

**Pass:**
- Timestamped duplicates such as `goalkeeper_daniel_cohen_20260531_183000.txt` collapse to one sidebar row: `goalkeeper_daniel_cohen.txt`
- Genuinely different files (Daniel, Yossi, Omer, Marco CVs; `*_report.txt`) remain distinct
- No S3 objects are deleted

---

## Test F3 — Multiple exact-match candidates

Ask the full Hebrew recruitment question (5 years, calm, build-up, north relocation, up to 80,000 EUR).

**Pass:**
- Answer briefly acknowledges **every** candidate with `all_mandatory_pass=YES` in the verified matrix (e.g. Daniel Cohen and Marco Silva when both qualify)
- Answer must **not** describe an exact-match candidate's verified PASS field as missing, unknown, insufficient, or failed
- States a preferred recommendation only when scouting evidence supports a distinction
- If documents do not justify a unique winner, answer states uncertainty rather than inventing a tie-breaker
- If Bedrock still contradicts the matrix after one retry, a deterministic ScoutMatch fallback answer is returned (`generation_mode`: `aws_kb_exact_match_fallback`)

**Parser note:** Marco Silva and other CVs should include structured compact fact fields when possible. Narrative phrases such as "build-up specialist" or "composed under pressure" are used only when structured fields are absent.

---

## Test F4 — Exact-match compliance retry and fallback

1. Ask the full Hebrew recruitment question in a clean session
2. Inspect the answer and `generation_mode` in the API response (or browser network tab)

**Pass:**
- Every exact-match candidate is named
- No PASS field is misrepresented for an exact-match candidate
- At most one exact-match acknowledgment retry occurs before fallback
- Fallback (if used) lists verified values only and states uncertainty when multiple exact matches exist
- Source cards remain ScoutMatch-only; Main source remains recommendation-aware

---

## Test G — Strict out-of-domain refusal

Ask unrelated questions in **separate new sessions**:

```
מי זה דונלד טראמפ?
What is the capital of New Zealand?
```

**Pass:**
- Exact Hebrew refusal: `אין לי מספיק מידע במסמכי השחקנים ובמסמכי הקבוצה כדי לענות על השאלה הזאת.`
- Exact English refusal: `I do not have enough information in the uploaded player and team documents to answer this question.`
- **No source cards** attached
- No general-knowledge fallback

---

## Test G2 — Follow-up with football context

1. In one session ask: `מי השוער המתאים ביותר למשחק רגל?`
2. Then ask: `ומה השכר שלו?`

**Pass:** Follow-up allowed when prior messages contain football-player context; salary grounded from CVs.

---

## Test G3 — Diverse comparison sources

Ask a full recruitment comparison (Hebrew 5-year / 80k / north relocation question).

**Pass:** Source cards include multiple unique goalkeeper CVs, scouting reports, and `team_requirements.txt` — not repeated chunks from a single file only.

---

## Test H — Confirm refusal styling

Answer should appear as refusal (no invented political facts)

---

## Test I — Live upload demo

Upload:
`sample_scout_data/demo_upload_later/goalkeeper_marco_silva.txt`

**Pass:** Upload + ingestion starts

---

## Test J — Wait for sync

Wait until ingestion **COMPLETE**

---

## Test K — Re-ask goalkeeper question

Ask:
```
מי השוער המתאים ביותר להנעת כדור מאחור?
```

**Pass:** Marco Silva mentioned when relevant; new source in list

---

## Test L — New conversation preserves documents

1. Click **New conversation**
2. Check document list in sidebar

**Pass:** S3 documents still listed; no destructive reset

---

## Test M — Delete conversation

1. Delete a conversation
2. Confirm documents remain

**Pass:** Chat removed; KB files unchanged

---

## Test N — Docker verification

```powershell
docker build -t scoutmatch-ai .
docker run --rm --env-file .env -p 5000:5000 scoutmatch-ai
```

Verify:
- `curl http://127.0.0.1:5000/api/health` → `"ok": true`
- `curl http://127.0.0.1:5000/api/status` → ScoutMatch fields present
- Browser opens homepage

---

## Test O — EC2 global access (later)

1. Deploy per `EC2_DEPLOYMENT_GUIDE.md`
2. Open `http://EC2_PUBLIC_IP` from phone
3. Confirm chat and upload work

**Pass:** App reachable globally on port 80

---

## API quick checks

```bash
curl -s http://127.0.0.1:5000/api/health
curl -s http://127.0.0.1:5000/api/status
curl -s http://127.0.0.1:5000/api/documents
```

Never paste real `.env` values into tickets or commits.

---

## Recommendation quality checklist

After asking a recruitment question (especially in Hebrew), verify:

| Check | Pass criteria |
|-------|----------------|
| Player name explicit | Answer names the recommended player by full name (e.g. Daniel Cohen, Marco Silva) |
| No internal markers | Answer must **not** contain `Passage %[1]%`, `%[4]%`, or similar Bedrock placeholders |
| Numeric requirements | A player with 4 years must **not** be said to meet a minimum of 5 years; salary and relocation must be checked accurately |
| Same language | Hebrew question → Hebrew answer; English question → English answer |
| Sources shown | **Main source** and **Retrieved evidence** list readable filenames such as `goalkeeper_daniel_cohen.txt` |
| No invented facts | Skills, clubs, salaries, or preferences not in documents must not appear |
| Partial matches labeled | If no exact match, answer states no full match and explains unmet requirements |
| Strict refusal | Unrelated or unsupported questions still receive the strict refusal message |
| AI-assisted label | Recommendation clearly framed as document-based AI assessment, not a guaranteed decision |

**Fail examples to watch for:**
- "the one highlighted in Passage %[4]%"
- "4 years meets the requirement of at least 5 years"
- Generic answer with no player name when documents name candidates

---

## Test P — Clean final-demo sequence (required before production demo)

Complete these steps in order after local code fixes and **before** the final live presentation.

### P1 — Clean ScoutMatch test files from S3

Follow `SCOUTMATCH_S3_CLEANUP_GUIDE.md`:

1. List objects under `scoutmatch/knowledge-base/` only
2. Remove temporary test uploads from that prefix
3. Do **not** delete unrelated S3 prefixes

### P2 — Sync empty data source

1. Trigger sync (`POST /api/ingestion/sync` or sidebar action)
2. Wait until status = **COMPLETE**

### P3 — Upload clean initial goalkeeper dataset

Upload through the website (wait for sync after uploads if needed):

- `sample_scout_data/team_requirements.txt`
- `sample_scout_data/player_cvs/goalkeeper_daniel_cohen.txt`
- `sample_scout_data/scouting_reports/goalkeeper_daniel_cohen_report.txt`
- `sample_scout_data/player_cvs/goalkeeper_yossi_levi.txt`
- `sample_scout_data/scouting_reports/goalkeeper_yossi_levi_report.txt`
- `sample_scout_data/player_cvs/goalkeeper_omer_azulay.txt`
- `sample_scout_data/scouting_reports/goalkeeper_omer_azulay_report.txt`

**Do not upload Marco Silva yet.**

### P4 — Ask Hebrew goalkeeper question

```
אני מחפש שוער עם ניסיון, רגוע תחת לחץ וטוב במשחק רגל. מי מתאים?
```

**Pass:**
- Explicit player **full name**
- Valid numeric reasoning (no 4-years-meets-5-years errors)
- Answer in **Hebrew**
- Readable sources with CV/report filenames

### P5 — Ask unrelated question (strict refusal)

```
מי זה דונלד טראמפ?
```

**Pass:** Hebrew refusal; no invented facts

### P6 — Late demo: upload Marco Silva only

Upload:
```
sample_scout_data/demo_upload_later/goalkeeper_marco_silva.txt
```

Wait for ingestion **COMPLETE**.

### P7 — Re-ask recruitment question

Ask the same Hebrew goalkeeper question (or the English 5-year / relocation / salary brief).

**Pass:**
- Recommendation changes or expands with **Marco Silva** when documents support it
- No `Passage %[N]%` markers
- No vague "the candidate" without a name
- Marco Silva CV shows **7 years** experience consistently

### P8 — Confirm runtime quality

| Check | Pass criteria |
|-------|----------------|
| No passage markers | No `Passage %[4]%`, `%[4]%`, or "highlighted in" |
| Explicit naming | Full player name in recommendation answers |
| Numeric logic | 4 years must not satisfy minimum 5 years |
| Neutral sources | Retrieved evidence has no "TOP RECOMMENDATION" lines |
| Strict refusal | Broken or ungrounded answers return refusal text |
