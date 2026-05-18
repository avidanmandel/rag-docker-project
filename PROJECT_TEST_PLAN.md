# Project test plan — `Avidan_RAG_Docker_Project`

Fill **Actual result / PASS/FAIL** when you demo (after `docker build` / `docker run` with a local `.env` only — never submit `.env`).

## Core scripted questions

| Test ID | Test question / action | Expected result |
|---------|--------------------------|----------------|
| PT-01 | **What is Flask?** | Grounded reply from Flask lecture PDF; **Main source** + sources list; reply should **not** start with `"I could not find this in the documents..."`. |
| PT-02 | **What is Docker?** | Grounded reply referencing `docker_aws.pdf`; sources visible. |
| PT-03 | **What is the difference between Docker containers and virtual machines?** | Answer from Docker/AWS PDF; mixed sources acceptable. |
| PT-04 | **What is the project codename in the uploaded document?** | **`Blue Falcon`**, citations from **`upload_test_knowledge_base.pdf`**. |
| PT-05 | **What is the secret verification code?** | **`RAG-777`**, same PDF source metadata. |
| PT-06 | **What was my last question?** (after PT-05) | Reply from SQLite / chat history; ideally **empty** irrelevant document sources (`context` []). |
| PT-07 | **What is the capital of France?** | Starts with **`I could not find this in the documents. Based on general knowledge,`**; mentions Paris; **no** document sources displayed. |

## Docker sanity

| Test ID | Check | Expected |
|---------|-------|----------|
| PT-D1 | `docker build -t avidan-rag-docker-project .` | Build succeeds |
| PT-D2 | `docker ps` → `avidan-rag-test` | `0.0.0.0:5000->5000/tcp` |
| PT-D3 | `docker logs avidan-rag-test` | Flask on `0.0.0.0` → RAG **Ready** line |

## Upload sanity

| Test ID | Action | Expected |
|---------|--------|----------|
| PT-U1 | Upload a small `.pdf` from sidebar | Toast + file in sidebar list + `/api/status` rebuild + `chunks` updated |
| PT-U2 | Upload a `.png`/`.jpg`/`.webp` (**text + photo objects**) (`GEMINI_API_KEY` optional*) | Busy→ internal `generated/*.extracted.txt` merges **Gemini Vision** scene + OCR, or (**quota**) **Tesseract OCR** (`heb+eng`) only; sidebar shows exactly **one IMAGE row** |
| PT-U3 | Upload a **scanned** PDF or image-heavy lecture export | Sparse pages OCR via rendered bitmap + **Tesseract**; chunk text prefixed with **`[Scanned or image-heavy PDF page…]`**; citations **`filename.pdf p.N`** |

## Visual understanding sanity (Bird / castle / ball style photo)

Ideal setup: illustrative photo with recognizable objects (**no OCR required**).

| Step | Action | Expected |
|------|--------|----------|
| PT-VIS-1 | With quota, upload photo + wait `ready=true` | Extracted KB text includes Gemini **scene description**; questions like *“What appears in the image?”* cite friendly filename |
| PT-VIS-2 | **`מה מופיע בתמונה?`** (same upload) | Assistant references objects listed in Gemini description chunk |
| PT-VIS-3 | Simulate quota exhaustion (or disable Vision) → upload photo + OCR-only index (`# kb_gemini_visual: no`) | Visual prompts (*מה מופיע…*, *explain the image*) get the bilingual **Gemini quota / OCR-only** reply; OCR-only prompts (*what text/code*) still retrieve `IMG-555`/`Dolphin` style answers |

## Image OCR / quota fallback (manual fixture)

Create a PNG (or JPG) containing:

```
Image Test Code: IMG-555
Project Animal: Dolphin
```

| Step | Action | Expected |
|------|--------|----------|
| PT-OCR-1 | Upload the fixture (**Upload** button) while Gemini quota may or may not be available | Busy state → toast either *“converted to text with Gemini Vision”* OR *“text extracted with local OCR fallback”* |
| PT-OCR-2 | Sidebar / `GET /api/documents` / `/api/status` | Sidebar shows **one IMAGE** row per uploaded raster; **`GET /api/documents`** may include `internal_text_source` metadata but the UI hides internal paths—**`.extracted.txt` is never a separate Knowledge Base row**; **`ready=true`** after reindex |
| PT-OCR-3 | Ask: **What is the image test code?** | Answer **`IMG-555`**, **Main source** shows the **friendly upload filename** (e.g. `fixture.png`) — not `generated/*.extracted.txt` |
| PT-OCR-4 | Ask: **What is the project animal?** | Answer **`Dolphin`** from the same OCR/Vision excerpts; **friendly image filename** in sources |
| PT-OCR-5 | Hebrew: **`מה מופיע בתמונה שהעליתי?`** (after uploading an image fixture) | Answer grounded on latest upload OCR/Vision chunk; prevents spurious grounding to `docker_aws.pdf`; **Main source** shows the raster filename |

## Chat QA when Gemini text generation quota is exhausted (manual)

| Step | Prompt | Expected |
|------|--------|----------|
| PT-CHAT-1 | After uploading the IMG-555/Dolphin OCR fixture (`*.extracted.txt` indexed), ask **English**: `What is the image test code?` | **`IMG-555`** (possibly with OCR glyph fixes) surfaced from retrieved excerpts; **Main source/image filename** cites the raster name, not `.extracted.txt` |
| PT-CHAT-2 | Same KB, ask **Hebrew**: `מה קוד הבדיקה בתמונה?` | Still surfaces **`IMG-555`** plus cyan-accent **retrieval-fallback assistant bubble** noting Gemini is offline |
| PT-CHAT-3 | Ask: `מה החיה של הפרויקט?` or English `What is the project animal?` | **`Dolphin`** surfaced from excerpts |
| PT-CHAT-4 | Inspect assistant bubble classes | Gemini-offline replies use `generation_mode: retrieval_fallback` (cyan border) rather than dumping raw HTTP/JSON errors |

---

## Submission rubric — reset & multimodal KB (manual)

Fill **PASS/FAIL** when demonstrating features.

| # | Action | Expected |
|---|--------|----------|
| 1 | Click **New conversation** | Chat is empty/new; Knowledge Base file list unchanged (same PDFs/uploads still listed after refresh). |
| 2 | Upload a **PDF** | PDF appears in Knowledge Base with **PDF** badge; after `ready=true`, RAG answers grounded from that PDF. |
| 3 | Upload an **image** with visible text (PNG/JPG/WEBP) | Accepted → success toast mentions Vision/OCR indexing; sidebar shows **exactly one IMAGE badge** labeled with the raster filename (**no duplicated `.extracted.txt` Knowledge Base row**); RAG can answer after `ready=true`. |
| 4 | Ask a question about the **uploaded image** content | Answer cites the **friendly image filename**; retrieval uses OCR/Vision text internally without exposing `.extracted.txt` duplicate rows in sidebar |
| 5 | Click **Clear All / Reset Project** (confirm dialog exact copy) | SQLite sessions/messages cleared; uploads removed from `data/`; **`upload_test_knowledge_base.pdf`** archived to **`sample_uploads/`** if it was in `data/`; index rebuilt; only **starter** PDFs remain in Knowledge Base (`Flask-lecture1.pdf`, `Flask-lecture2.pdf`, `docker_aws.pdf`). |
| 6 | After Clear All, ask: **What is Flask?** | Still grounded answer from starter Flask lecture PDF(s). |
| 7 | After Clear All, ask about **prior uploaded PDF/image** content | Should **not** recall removed uploads unless uploaded again. |
| 8 | Upload unsupported type (e.g. `.exe`, `.zip`) | Friendly JSON/UI error; app stable (no crash). |
