# Manual test plan (`Avidan_RAG_Docker_Project`)

Run with a filled **`.env`** (never commit secrets). Prefer Docker; open **http://localhost:5000** and wait for sidebar **Ready**.

---

### Tests A–D — Offline quota / grounding

**Test A — Flask (documents clearly relevant)**

- Question: **`What is Flask?`**
- **Expected:** Grounded explanation from Flask lecture PDFs; **Main source** `Flask-lecture1.pdf` or `Flask-lecture2.pdf`.

**Test B — Docker (documents clearly relevant)**

- Question: **`What is Docker?`**
- **Expected:** Grounded explanation with **Main source** `docker_aws.pdf`.

**Test C — General knowledge (`France`)**

- Question: **`what is the capital of France?`**
- **If Gemini works:** **`Paris`** (with README fallback prefix when the fact is not in the PDFs).
- **If Gemini is quota-/service-unavailable:** only  
  **`I could not find this in the documents, and Gemini is currently unavailable because of quota or service limits.`**
- **Forbidden in assistant body:** the old phrase **`Closest retrieved passages`** and unrelated course-text dumps posing as answers.

**Test D — Typo Capital / France**

- Question: **`what is the capital of franch`**
- **If Gemini works:** Interpret as France → **Paris** (or clarify typo + Paris).
- **If Gemini unavailable:** Same clean quota/service message as Test C — **no** unrelated chunk dump, **no** **`Closest retrieved passages`**.

---

### Test 1 — Docker build and run

Inside the project folder:

```powershell
docker build -t avidan-rag-docker-project .
docker run --rm --env-file .env -p 5000:5000 --name avidan-rag-test avidan-rag-docker-project
```

Expect: container starts without errors.

---

### Test 2 — localhost opens

Open **http://localhost:5000** — UI loads.

**Health:**

- **GET** http://localhost:5000/api/health — JSON with `rag_ready`, `flask: running`.
- **GET** http://localhost:5000/api/status — `ready: true` when indexing finished.

---

### Test 3 — Base PDF question: What is Flask?

**Expected:** Grounded reply; expanded sources cite a **Flask lecture** PDF (e.g. `Flask-lecture1.pdf` or `Flask-lecture2.pdf`).

---

### Test 4 — Docker question: What is Docker?

**Expected:** Sources include **`docker_aws.pdf`** when retrieval hits course material.

---

### Test 5 — General question: what is the capital of France?

- **If Gemini works:** Answer **Paris**, with the README-prescribed fallback prefix when the documents do not contain the fact.
- **If Gemini quota / service down:** Expect the clean English line (when no strong doc match offline):  
  `I could not find this in the documents, and Gemini is currently unavailable because of quota or service limits.`  
  Do **not** expect raw API errors or random unrelated chunk dumps for weak matches.

---

### Test 6 — Memory

Ask:

`what is the capital of France?`

Then:

`what was the last question i asked?`

**Expected:** Assistant refers to the earlier question from **chat history** (SQLite-backed session).

---

### Test 7 — TXT upload

Upload **`for_check.txt`** containing (Hebrew fixtures):

```
קוראים לי רועי בן אביתר
832 אני בן
אני אוהב לאכול במבה
לא אוהב לשתות נוטלה עם קפה
```

Poll **Until Ready**. Then:

| Question | Expected gist |
|---------|----------------|
| `בן כמה רועי?` | Answer includes **832**; **Main source**: `for_check.txt` **p.1**. |
| `מה רועי אוהב לאכול?` | **מבה** (or semantic equivalent). |
| `מה רועי לא אוהב לשתות?` | **נוטלה עם קפה** (or semantic equivalent). |

---

### Test 8 — PDF upload

Use **`sample_uploads/upload_test_knowledge_base.pdf`** (fixture) or recreate a PDF stating:

> Project codename: Blue Falcon  
> Secret verification code: RAG-777  
> This document is used to test PDF upload.

Upload, wait **Ready**.

| Question | Expected |
|---------|----------|
| What is the project codename? | **Blue Falcon**; **`upload_test_knowledge_base.pdf`** **p.1**. |
| What is the secret verification code? | **RAG-777**; same source/page. |

---

### Test 9 — Clear All / Reset Project

After uploads, confirm **Clear All / Reset Project**.

**Expected:**

- Conversations emptied; UI chat cleared.
- User-uploaded TXT/PDF under `data/` removed.
- Starter files remain in `data/`:
  - `Flask-lecture1.pdf`
  - `Flask-lecture2.pdf`
  - `docker_aws.pdf`
- Status returns **Ready** after re-index.

---

### Test 10 — Submission folder clean (before ZIP)

Confirm the archive **does not** include:

- `.env`
- API keys pasted into any file
- `chat.db`
- `rag_history.db`
- `__pycache__` / `.pyc`
- `.venv`
- `index_cache/`
- `app.log`
- Personal uploads (resume, private PDFs unless required by course)
