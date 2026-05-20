aouther avidan

# Course Assistant — Flask, Docker & AWS (RAG)

A Retrieval-Augmented Generation (RAG) web application that answers questions
about Flask, Docker, and AWS **using course materials first**. Retrieval uses
**Hugging Face embeddings + FAISS**; answers are produced with **Google Gemini**
when generation is enabled.

**How out-of-scope and “no good document hit” cases work**

- The app **first** tries the **knowledge base** (retrieve relevant chunks,
  relevance thresholds, grounded prompts).
- If **no relevant document-backed answer** is found, it **may use a Gemini
  general-knowledge fallback** when the Gemini API is available (expected prefix:
  `I could not find this in the documents. Based on general knowledge,`).
- If **Gemini is unavailable** because of quota or service limits (or similar),
  the assistant returns a **clean unavailable message** instead of stuffing the
  reply with **unrelated random document excerpts**.

Gemini **text generation** is configured through **`GEMINI_MODEL`** in `.env`
(see **`config.py`**). **Default used in this project:** **`gemini-2.5-flash`**.
.

---

## Topic

Starter PDFs in `data/`:

| File | Topic |
|------|-------|
| `Flask-lecture1.pdf` | Flask basics: app object, routes, templates |
| `Flask-lecture2.pdf` | Flask continued: forms, request handling |
| `docker_aws.pdf` | Docker fundamentals and AWS deployment notes |

---

## Architecture

```
                    +------------------+
PDFs in data/  -->  |  pdf_loader.py   |  page-level text (PyMuPDF + optional OCR)
                    +------------------+
                            |
                            v
                    +------------------+
                    |    chunker.py    |  ~700 char windows, overlap
                    +------------------+
                            |
                            v
                +--------------------------+
                |  Hugging Face Inference  |  embeddings (cloud)
                +--------------------------+
                            |
                            v
                +--------------------------+
                |   FAISS (IndexFlatIP)    |  cosine via L2-normalised IP
                |   cache: index_cache/   |
                +--------------------------+
                            |
        user question --->  | retrieve top-K, MIN_SCORE_THRESHOLD
                            v
                +--------------------------+
                | Google Gemini            |  GEMINI_MODEL via .env
                | (generation + routing)   |  default: gemini-2.5-flash
                +--------------------------+  (see rag_engine prompts)
                            |
                            v
                +--------------------------+
                | Flask + SQLite + static  |  `/api/sessions`, upload, reset
                +--------------------------+
```

### Components

- **`pdf_loader.py`** — PDF text via **PyMuPDF**, optional **Tesseract** where needed;
  plain `.txt` from `data/`.
- **`chunker.py`** — sliding windows (~700 chars, overlap); keeps source + page.
- **`rag_engine.py`** — embedding, FAISS, retrieval, Gemini answering, quota /
  retrieval-fallback behaviour (`generation_mode` when Gemini is constrained).
- **`image_extract.py`** — image uploads → Vision/OCR-derived text paths used by indexing.
- **`database.py`** — SQLite `sessions` / `messages` for conversation memory.
- **`app.py`** — Flask routes: `/`, `/api/status`, `/api/documents/upload`,
  **`POST /api/reset-all`**, sessions, chat, health.
- **`templates/`**, **`static/`** — sidebar chat UI including **Clear All / Reset Project**.

### Design notes

| Decision | Reason |
|---------|--------|
| **HF Inference API embeddings** | Matches class tooling; avoids large local downloads. |
| **FAISS `IndexFlatIP`** + normalised vectors | Cosine retrieval suited to a compact KB. |
| **`GEMINI_MODEL` in `.env`** | Switch models without code changes; project default **`gemini-2.5-flash`**. |
| **Index cache** | Faster warm starts after the first embed/build. |

---

## Setup

Requires Python 3.10+ (or use Docker only).

```powershell
cd Avidan_RAG_Docker_Project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env` from the example (**never commit real keys**):

```powershell
copy .env.example .env
notepad .env
```

Fill placeholders (names only):

```
GEMINI_API_KEY=
HF_TOKEN=
GEMINI_MODEL=gemini-2.5-flash
```

Adjust **`GEMINI_MODEL`** if your course account uses another allowed model string.

---

## Run (local Python)

```powershell
python app.py
```

Open <http://127.0.0.1:5000>.

---

## Run with Docker (Windows PowerShell)

Work inside **`Avidan_RAG_Docker_Project`**.

1. **`copy .env.example .env`** then edit **`GEMINI_API_KEY`**, **`HF_TOKEN`**, and
   optionally **`GEMINI_MODEL`**.
2. **Build**

   ```powershell
   docker build -t avidan-rag-docker-project .
   ```

3. **Run** (recommended names for demos / screenshots):

   ```powershell
   docker run --rm --env-file .env -p 5000:5000 --name avidan-rag-test avidan-rag-docker-project
   ```

4. Open **<http://localhost:5000>**. The image listens on **`0.0.0.0:5000`**
   (**`FLASK_HOST`**).

### Files excluded from the image / submission

Runtime-only paths (also in `.dockerignore` / `.gitignore`):

- `.env` - secrets
- `app.log`, `*.log`
- `chat.db`, `rag_history.db`
- `index_cache/`
- `__pycache__/`, `*.pyc`
- `.venv/`, `venv/`

---

## How a question flows (high level)

1. Embed the question; query FAISS for top‑K chunks; filter by **`MIN_SCORE_THRESHOLD`** (see `.env` / **`config.py`**).
2. If **documents** justify an answer → grounded reply with **`Main source`** / sources in the UI when applicable.
3. If **documents do not suffice** → **Gemini general fallback** **when available**, with the fixed **“could not find in documents…”** prefix.
4. If **Gemini cannot run** (quota / limits) → user-visible **quota / unavailable** wording **without** returning irrelevant course snippets as if they answered the question.

---

## Clear All / Reset Project (UI + API)

The sidebar **Clear All / Reset Project** control calls **`POST /api/reset-all`**
with JSON **`{"confirm": true}`**. It clears **all** conversations, removes
**uploads** under `data/` while **keeping only** **`Flask-lecture1.pdf`**,
**`Flask-lecture2.pdf`**, **`docker_aws.pdf`**, clears generated/index cache state
per **`app.py`**, and kicks off a background **`engine.reindex()`**.

See **`MANUAL_TESTS.md`** for a short manual checklist including reset.

---

## API (selected)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/status` | Engine readiness, chunk count, progress, optional `error` payload |
| `GET` | `/api/health` | Lightweight Flask + RAG high-level flags |
| `GET` | `/api/documents` | Sidebar knowledge-base listing (PDF/TXT/IMAGE rows) |
| `POST` | `/api/documents/upload` | Multipart **`file`** — PDFs/TXT to `data/`; images through Vision/OCR pipeline |
| `POST` | `/api/reset-all` | **Clear conversations** and **uploaded KB files**, **keep starter PDFs** above. Requires JSON body **`{"confirm": true}`** (boolean). Returns JSON success (`ok`) and triggers re-index in the background |
| `GET` / `POST` / … | `/api/sessions` … | Session CRUD |
| `POST` | `/api/sessions/<id>/messages` | Ask a question → answer (+ grounded `context` when document-backed) |

---

## Testing

| Resource | Purpose |
|----------|---------|
| **`MANUAL_TESTS.md`** | Manual UI checklist (Docker, uploads, Clear All). |
| **`TEST_QUESTIONS.md`** | Scripted question examples. |
| `python tests/test_rag.py` | Direct engine / integration checks (needs keys where applicable). |

---

## Reflection

**What worked well**

- Small modules (`pdf_loader`, `chunker`, `rag_engine`, `database`, `app`) keep
  the pipeline easy to test and reason about.
- Cached FAISS artifacts make repeat runs much faster than cold embedding.
- Explicit separation between **document answers**, **memory-style** chat, and
  **general fallback** (plus quota handling) keeps behaviour predictable.

**What could improve**

- PDF-aware chunking (slides, headings) for cleaner citations.
- Optional local embeddings to reduce cloud dependency for demos.
- Tunable thresholds with a small labelled evaluation set.

---

## License / course context

Educational Flask + Docker project — supply your own **Gemini** and **Hugging Face** credentials via `.env`.
