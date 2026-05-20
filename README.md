# Avidan RAG Docker Project

**Author:** Avidan Mandelman

A strict Retrieval-Augmented Generation (RAG) web assistant that answers questions **only from indexed documents** in the knowledge base. The app combines a **Flask** chat UI, **Hugging Face** embeddings, a **FAISS** vector index, and **Google Gemini** for grounded generation.

---

## Project description

This project implements a document-grounded course assistant. Users ask questions in English or Hebrew; the system retrieves relevant PDF/TXT chunks, sends **only that context** to Gemini, and returns an answer with source citations. If no relevant document evidence is found, the assistant refuses with a clear no-information message — it does **not** fall back to Gemini general knowledge.

---

## Topic / purpose

Build a production-style RAG pipeline inside Docker that:

- Indexes starter course and project documents from `data/`
- Allows temporary PDF/TXT uploads during a conversation
- Enforces strict document-only answers with visible sources
- Resets session uploads on **New conversation** while keeping protected starter files

---

## Knowledge base documents

Protected starter files (always kept in `data/`):

| File | Description |
|------|-------------|
| `Avidan Risk Analysis Report.txt` | Risk analysis report (NIS2 / energy-grid) |
| `docker_aws.pdf` | Docker fundamentals and AWS deployment notes |
| `Flask-lecture1.pdf` | Flask basics: app object, routes, templates |
| `Flask-lecture2.pdf` | Flask continued: forms, request handling |
| `for_check.txt` | Small TXT test file (Hebrew content for bilingual retrieval tests) |

Users can also **upload PDF or TXT files** during a conversation via the Knowledge Base panel. Uploaded files are indexed immediately and become available for questions in the current session.

**Temporary uploads:** files added during a conversation are removed when the user starts a **New conversation** or runs **Clear All / Reset Project**. The five starter files above are always preserved.

---

## Strict RAG behaviour

- The assistant answers **only** from retrieved, indexed document chunks.
- Gemini receives **retrieved context only** — no general-knowledge fallback.
- If no chunk passes the relevance threshold, or the context does not support an answer, the assistant returns:
  - **EN:** *"I do not have enough information in the provided documents to answer this question."*
  - **HE:** *"אין לי מספיק מידע במסמכים הקיימים כדי לענות על השאלה הזאת."*
- Source file names and pages are cited in answers when possible.

---

## Architecture

```
                    +------------------+
PDF/TXT in data/ -> |  pdf_loader.py   |  page-level text (PyMuPDF + optional OCR)
                    +------------------+
                            |
                            v
                    +------------------+
                    |    chunker.py    |  ~700 char windows with overlap
                    +------------------+
                            |
                            v
                +--------------------------+
                |  Hugging Face Inference  |  cloud embeddings
                +--------------------------+
                            |
                            v
                +--------------------------+
                |   FAISS (IndexFlatIP)    |  cosine similarity search
                |   cache: index_cache/    |
                +--------------------------+
                            |
        user question --->  | retrieve top-K, relevance filter
                            v
                +--------------------------+
                | Google Gemini            |  grounded generation only
                | (GEMINI_MODEL via .env)  |
                +--------------------------+
                            |
                            v
                +--------------------------+
                | Flask + SQLite + static  |  chat UI, upload, reset
                +--------------------------+
```

### Components

| Module | Role |
|--------|------|
| `app.py` | Flask routes: chat, sessions, upload, reset |
| `pdf_loader.py` | Load PDF/TXT from `data/` |
| `chunker.py` | Split documents into searchable chunks |
| `rag_engine.py` | Embeddings, FAISS retrieval, strict Gemini answering |
| `database.py` | SQLite conversation history |
| `templates/`, `static/` | Web UI (no general-knowledge mode) |

---

## Setup — environment variables

Copy the example file and fill in your keys locally (**never commit `.env`**):

```powershell
copy .env.example .env
notepad .env
```

Required variables:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for grounded text generation |
| `HF_TOKEN` | Hugging Face token for embedding API calls |
| `GEMINI_MODEL` | Gemini model name (default in `.env.example`: `gemini-2.5-flash`) |

---

## Run locally (Python)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>.

---

## Run with Docker

From the project root:

```powershell
copy .env.example .env
# Edit .env with your keys

docker build -t avidan-rag-docker-project .
docker run --rm --env-file .env -p 5000:5000 --name avidan-rag-test avidan-rag-docker-project
```

Open <http://localhost:5000>.

---

## Testing / validation

Example queries and expected behaviour:

| # | Question | Expected result |
|---|----------|-----------------|
| 1 | `what is the capital city of france?` | **Paris / פריז** from `for_check.txt` (bilingual retrieval) |
| 2 | `what is the capital of iceland?` | No-information answer (Iceland not in documents) |
| 3 | `Who is the owner of the Risk Analysis Report?` | **CRO** from `Avidan Risk Analysis Report.txt` |
| 4 | `What is Docker?` | Grounded answer from `docker_aws.pdf` with source citation |
| 5 | Upload resume PDF, ask where Avidan studied | Answer from uploaded resume with source citation |
| 6 | **New conversation / reset** | Uploaded files removed; starter files remain; index rebuilt |

Automated checks (requires `.env` keys):

```powershell
python tests/test_rag.py
python tests/run_final_verification.py
```

See also `MANUAL_TESTS.md` and `TEST_QUESTIONS.md`.

---

## Screenshots

Submission screenshots are in [`screenshoot/`](screenshoot/):

| File | Description |
|------|-------------|
| [01_home_knowledge_base_ready.png](screenshoot/01_home_knowledge_base_ready.png) | Home screen with knowledge base ready |
| [02_for_check_hebrew_source_answer.png](screenshoot/02_for_check_hebrew_source_answer.png) | Hebrew question answered from `for_check.txt` |
| [03_bilingual_france_for_check_source.png](screenshoot/03_bilingual_france_for_check_source.png) | English France question retrieved from Hebrew TXT |
| [04_docker_pdf_source_answer.png](screenshoot/04_docker_pdf_source_answer.png) | Docker question with PDF source citation |
| [05_strict_rag_no_general_knowledge.png](screenshoot/05_strict_rag_no_general_knowledge.png) | Out-of-scope question refused (no general knowledge) |
| [06_uploaded_resume_source_answer.png](screenshoot/06_uploaded_resume_source_answer.png) | Uploaded resume answered with source |
| [07_txt_file_summary_for_check.png](screenshoot/07_txt_file_summary_for_check.png) | TXT file summary from `for_check.txt` |
| [08_delete_conversation_confirmation.png](screenshoot/08_delete_conversation_confirmation.png) | Delete conversation confirmation dialog |
| [09_home_after_reset_clean_state.png](screenshoot/09_home_after_reset_clean_state.png) | Clean home state after reset |

---

## Limitations / reflection

**What worked well**

- Modular pipeline (`pdf_loader` → `chunker` → FAISS → Gemini) is easy to test and extend.
- Strict RAG prevents hallucinated answers outside the knowledge base.
- Session-scoped uploads let users add private documents without permanently changing the starter KB.
- Bilingual retrieval aliases help English questions find Hebrew document evidence.

**Limitations**

- Works best with **text-based PDF and TXT** files.
- **Complex table-based Hebrew PDFs** (e.g. grade sheets) may be extracted less accurately because layout/table structure is hard to preserve.
- Embedding and generation depend on external APIs (Hugging Face + Gemini).

**Future improvements**

- Better OCR and table extraction for scanned or tabular PDFs.
- PDF-aware chunking (headings, slide boundaries) for cleaner citations.
- Optional local embeddings for offline demos.

---

## License / course context

Educational Flask + Docker + RAG project. Supply your own **Gemini** and **Hugging Face** credentials via `.env`.
