# Final submission checklist — `Avidan_RAG_Docker_Project`

Verify each row manually (with your **local-only** `.env` for Docker demos). Submit **ZIP without** `.env`, keys in screenshots blurred.

| Requirement | Evidence / where to check | PASS | Screenshot? |
|-------------|---------------------------|:----:|:-----------:|
| Flask backend | `app.py` mounts `/` + `/api/...` | ☐ | — |
| Local HTML/CSS/JS UI | `templates/`, `static/` | ☐ | Main chat page |
| RAG ingestion | `pdf_loader.py`, `chunker.py`, `/api/status` `chunks > 0` | ☐ | `/api/status` JSON |
| FAISS | `rag_engine.py`; logs `Building FAISS index` / `Ready. N vectors` | ☐ | Docker logs excerpt |
| Embeddings HF | Logs `Embedding chunks via Hugging Face` | ☐ | logs |
| Gemini generation | Responses for PT-07 fallback prefix | ☐ | chat bubble |
| SQLite memory | Sidebar sessions; `/api/sessions`; memory Q answers | ☐ | memory QA |
| PDF upload | `POST /api/documents/upload`; sidebar button | ☐ | before/after KB list |
| General-knowledge fallback | Answer starts `"I could not find this in the documents. Based on general knowledge,"` | ☐ | France question |
| Doc-grounded citations | Main source banner + expandable list | ☐ | Flask QA |
| `Dockerfile` + `.dockerignore` | Repo root files | ☐ | file tree |
| Docker build/run | `docker build -t avidan-rag-docker-project .` + mapped run | ☐ | terminal + browser |
| README complete | Describes topic, architecture, SQLite, uploads, `.env.example`, screenshots | ☐ | PDF export |
| No secrets submitted | Folder contains **no** `.env`; `.env.example` empty placeholders | ☐ | zip inspection |

Legend: PASS when satisfied after your final demo refresh.
