"""
Flask web app exposing the RAG course assistant.

Two halves:
- HTML page at ``/`` rendering the chat UI
- JSON API under ``/api/...`` for status, sessions, and messages

The RAG engine is initialised in a background thread so the UI can render
immediately and poll ``/api/status`` for progress.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import traceback
import uuid

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

# Load environment variables from the local .env file before anything else
# touches os.environ. The .env file is never baked into the Docker image
# (see .dockerignore) and is supplied at runtime via `--env-file .env`.
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

import config  # noqa: E402  (must be imported after load_dotenv)
import database  # noqa: E402
from rag_engine import RAGEngine  # noqa: E402
from image_extract import (  # noqa: E402
    GeminiVisionError,
    is_quota_exhausted,
)


app = Flask(__name__)
engine = RAGEngine(gemini_api_key=GEMINI_API_KEY, hf_token=HF_TOKEN)
_init_error: dict | None = None


def _friendly_error(exc: Exception) -> dict:
    """Map raw exceptions to a short, user-facing message."""
    raw = str(exc)
    lowered = raw.lower()

    if is_quota_exhausted(exc):
        message = (
            "Google Gemini declined the request because of quota or rate limits "
            "(too many requests). Wait several minutes and try again. "
            "The app may still answer some questions using text retrieved from "
            "your documents when AI generation is skipped."
        )
    elif (
        "401" in raw
        or "unauthorized" in lowered
        or "invalid username or password" in lowered
        or "invalid api key" in lowered
        or "permission" in lowered
        or "forbidden" in lowered
    ):
        message = (
            "API key is missing or invalid. "
            "Please check GEMINI_API_KEY and HF_TOKEN in your .env file."
        )
    elif (
        "502" in raw
        or "503" in raw
        or "504" in raw
        or "service unavailable" in lowered
        or "temporarily unavailable" in lowered
        or "deadline exceeded" in lowered
        or "try again later" in lowered
    ):
        message = (
            "A hosted AI service (Gemini or Hugging Face) returned a temporary error "
            "or timeout. Wait a minute and retry; heavy traffic or maintenance can "
            "cause brief outages."
        )
    else:
        # Keep it short for the UI; full traceback is in the container logs.
        short = raw.splitlines()[0][:200]
        message = f"RAG engine failed to initialise: {short}"
    return {
        "message": message,
        "type": exc.__class__.__name__,
        "detail": raw,
    }


def _initialise_engine_background() -> None:
    global _init_error

    if not GEMINI_API_KEY or not HF_TOKEN:
        _init_error = {
            "message": (
                "API key is missing. Please check your .env file "
                "(GEMINI_API_KEY and HF_TOKEN must be set) "
                "and restart the container."
            ),
            "type": "MissingApiKey",
            "detail": "GEMINI_API_KEY or HF_TOKEN is empty.",
        }
        print("[init] " + _init_error["message"], flush=True)
        return

    try:
        engine.initialise()
    except Exception as exc:
        _init_error = _friendly_error(exc)
        traceback.print_exc()


def _start_background_init() -> None:
    database.init_db()
    threading.Thread(
        target=_initialise_engine_background, daemon=True, name="rag-init"
    ).start()


def _reindex_engine_background() -> None:
    """Run after an upload: rebuild the FAISS index in a background thread."""
    global _init_error
    _init_error = None
    try:
        engine.reindex()
    except Exception as exc:
        _init_error = _friendly_error(exc)
        traceback.print_exc()


STARTER_KB_FILES = config.STARTER_KB_FILES
SAMPLE_FIXTURE_PDF = "upload_test_knowledge_base.pdf"

DOC_UPLOAD_EXTENSIONS = {".pdf", ".txt"}
IMAGE_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
UPLOAD_ALLOWED_EXTENSIONS = DOC_UPLOAD_EXTENSIONS | IMAGE_UPLOAD_EXTENSIONS
UPLOAD_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _sync_sample_fixture_into_archive() -> None:
    """Keep ``upload_test_knowledge_base.pdf`` in ``sample_uploads/`` before wiping data."""
    src = config.DATA_DIR / SAMPLE_FIXTURE_PDF
    if not src.is_file():
        return
    config.SAMPLE_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, config.SAMPLE_UPLOADS_DIR / SAMPLE_FIXTURE_PDF)


def _purge_generated_tree() -> None:
    if config.GENERATED_DIR.exists():
        shutil.rmtree(config.GENERATED_DIR, ignore_errors=True)


def _purge_non_starter_kb_files() -> None:
    """Remove every file/dir under ``data/`` except protected starter KB files."""
    root = config.DATA_DIR
    for entry in list(root.iterdir()):
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
            continue
        if entry.is_file() and entry.name not in STARTER_KB_FILES:
            try:
                entry.unlink()
            except OSError:
                pass


def _purge_index_cache_files() -> None:
    """Remove every file under ``index_cache/`` (FAISS + manifest + any extras)."""
    cache = config.INDEX_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    for entry in list(cache.iterdir()):
        if entry.is_file():
            try:
                entry.unlink()
            except OSError:
                pass


def _reset_kb_to_starters() -> None:
    """Remove session uploads from ``data/``; keep starter KB files only."""
    _purge_generated_tree()
    _purge_non_starter_kb_files()
    _purge_index_cache_files()


def _reset_project_disk_and_cache() -> None:
    """SQLite cleared separately — wipe uploads/generated/cache snapshots."""
    _sync_sample_fixture_into_archive()
    _reset_kb_to_starters()


def _paired_extract_relative_for_image_basename(upload_basename: str) -> str | None:
    """Resolve ``generated/<stem>.extracted.txt`` paired with ``generated/images/`` file."""
    stem = Path(upload_basename).stem
    gen = config.GENERATED_DIR
    exact = gen / f"{stem}.extracted.txt"
    if exact.is_file():
        return exact.relative_to(config.DATA_DIR).as_posix()
    globs = sorted(
        gen.glob(f"{stem}_*.extracted.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if globs:
        return globs[0].relative_to(config.DATA_DIR).as_posix()
    return None


# ==========================================================
# ROUTES
# ==========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "ready": engine.ready,
        "status": engine.status,
        "chunks": len(engine.chunks),
        "sources": sorted({c.source for c in engine.chunks}) if engine.chunks else [],
        "progress": engine.progress,
        "error": _init_error,
    })


@app.route("/api/health")
def api_health():
    """Lightweight health check. Always returns 200 as long as Flask is up."""
    return jsonify({
        "ok": True,
        "flask": "running",
        "rag_ready": engine.ready,
        "rag_status": engine.status,
        "rag_error": _init_error["message"] if _init_error else None,
    })


@app.route("/api/debug/document-text")
def api_debug_document_text():
    """Optional extraction sanity check (disabled unless ALLOW_DEBUG_DOCUMENT_TEXT is set)."""
    flag = os.getenv("ALLOW_DEBUG_DOCUMENT_TEXT", "").lower()
    if flag not in ("1", "true", "yes"):
        return jsonify({"error": "Not found"}), 404
    if _init_error is not None:
        return jsonify({"error": "engine failed to initialise"}), 503
    if not engine.ready:
        return jsonify({"error": "engine not ready"}), 503

    name = (request.args.get("name") or "").strip()
    if not name or not re.fullmatch(r"[\w\-\.\s]+\.(pdf|txt)", name, flags=re.I):
        return jsonify({"error": "invalid name"}), 400

    target = (config.DATA_DIR / name).resolve()
    try:
        target.relative_to(config.DATA_DIR.resolve())
    except ValueError:
        return jsonify({"error": "invalid path"}), 400

    if not target.is_file():
        return jsonify({"exists": False, "error": "file not found"}), 404

    chunk_count = sum(
        1
        for c in engine.chunks
        if Path(c.source).name.lower() == name.lower()
    )

    if target.suffix.lower() == ".pdf":
        from pdf_loader import load_pdf

        pages_data = load_pdf(target)
        page_count = len(pages_data)
        blob = "\n".join(t for _, _, t in pages_data[:8])
    else:
        page_count = 1
        blob = target.read_text(encoding="utf-8", errors="ignore")

    preview = blob[:300]
    return jsonify({
        "exists": True,
        "name": name,
        "pages_extracted": page_count,
        "extracted_characters": len(blob),
        "chunks": chunk_count,
        "chunks_indexed_for_file": chunk_count,
        "text_preview_first_300_chars": preview,
        "first_text_preview": preview,
    })


# ---------- documents ----------

@app.route("/api/documents", methods=["GET"])
def api_list_documents():
    """Return user-visible KB rows (hide internal ``generated/*.extracted.txt`` listing)."""
    files: list[dict] = []
    try:
        root = config.DATA_DIR
        root.mkdir(parents=True, exist_ok=True)
        starter_order = {
            "Avidan Risk Analysis Report.txt": 0,
            "docker_aws.pdf": 1,
            "Flask-lecture1.pdf": 2,
            "Flask-lecture2.pdf": 3,
            "for_check.txt": 4,
        }

        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            norm = rel.replace("\\", "/")
            if norm.startswith("generated/"):
                continue
            suf = p.suffix.lower()
            if suf not in DOC_UPLOAD_EXTENSIONS:
                continue
            basename = Path(rel).name
            files.append({
                "name": rel,
                "display_source": basename,
                "size": p.stat().st_size,
                "ext": suf.lstrip("."),
                "category": "PDF" if suf == ".pdf" else "TXT",
            })

        img_dir = config.GENERATED_IMAGES_DIR
        if img_dir.is_dir():
            for p in sorted(img_dir.iterdir()):
                if not p.is_file():
                    continue
                suf = p.suffix.lower()
                if suf not in IMAGE_UPLOAD_EXTENSIONS:
                    continue
                internal = _paired_extract_relative_for_image_basename(p.name)
                entry: dict = {
                    "name": p.name,
                    "display_source": p.name,
                    "size": p.stat().st_size,
                    "ext": suf.lstrip("."),
                    "category": "IMAGE",
                    "hint": (
                        "Questions use searchable text or a Vision-generated description "
                        "saved from this image (indexed internally)."
                    ),
                }
                if internal:
                    entry["internal_text_source"] = internal
                files.append(entry)

        def _sort_kb_row(doc: dict) -> tuple:
            base = Path(doc["name"]).name
            if base in starter_order:
                return (0, starter_order[base])
            cat_pri = {"PDF": 10, "TXT": 11, "IMAGE": 12}
            return (
                1,
                cat_pri.get(str(doc.get("category", "")), 99),
                base.lower(),
            )

        files.sort(key=_sort_kb_row)
    except OSError:
        pass
    return jsonify({"documents": files})


@app.route("/api/documents/upload", methods=["POST"])
def api_upload_document():
    """Upload PDF/TXT to ``data/`` or images → Gemini Vision → ``generated/*.extracted.txt``."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "No file selected."}), 400

    safe_name = secure_filename(f.filename)
    if not safe_name:
        return jsonify({"error": "Invalid filename."}), 400

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in UPLOAD_ALLOWED_EXTENSIONS:
        allowed_human = ", ".join(sorted(UPLOAD_ALLOWED_EXTENSIONS))
        return jsonify({
            "error": (
                f"Unsupported file type '{ext}'. Allowed: {allowed_human}."
            ),
        }), 400

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    stored_paths: list[str] = []
    message_extra = "Poll /api/status until ready=true."
    upload_followup_note = ""

    try:
        if ext in DOC_UPLOAD_EXTENSIONS:
            dest = config.DATA_DIR / safe_name
            f.save(str(dest))
            size = dest.stat().st_size

            if size > UPLOAD_MAX_BYTES:
                try:
                    dest.unlink()
                except OSError:
                    pass
                return jsonify({
                    "error": (
                        f"File is too large ({size // 1024} KB). "
                        f"Max is {UPLOAD_MAX_BYTES // (1024 * 1024)} MB."
                    ),
                }), 413

            stored_paths.append(safe_name)
            headline = "File uploaded."

        elif ext in IMAGE_UPLOAD_EXTENSIONS:
            raw = f.read()
            image_sz = len(raw)
            if image_sz > UPLOAD_MAX_BYTES:
                return jsonify({"error": "Image is too large."}), 413

            mime = IMAGE_MIME_TYPES.get(ext)
            if not mime:
                return jsonify({"error": "Unsupported image MIME mapping."}), 400

            config.GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            img_dest = config.GENERATED_IMAGES_DIR / safe_name
            img_dest.write_bytes(raw)
            img_rel = img_dest.relative_to(config.DATA_DIR).as_posix()
            stored_paths.append(img_rel)

            try:
                outcome = engine.extract_image_for_kb(raw, mime)
            except GeminiVisionError as exc:
                traceback.print_exc()
                try:
                    img_dest.unlink()
                except OSError:
                    pass
                stored_paths.clear()
                return jsonify({"error": exc.public_message}), 422
            except Exception as exc:
                traceback.print_exc()
                try:
                    img_dest.unlink()
                except OSError:
                    pass
                stored_paths.clear()
                return jsonify({
                    "error": (
                        "Could not process this image right now. "
                        "Try again later or use a clearer screenshot."
                    ),
                }), 422

            if not outcome.text:
                msg = outcome.failure_message or (
                    "Image was uploaded, but no readable text was found to index."
                )
                return jsonify({
                    "error": msg,
                    "partial": True,
                    "stored_paths": stored_paths,
                }), 422

            kb_flag = "# kb_image_visual: yes\n" if outcome.has_visual_understanding else "# kb_image_visual: no\n"

            stem = Path(safe_name).stem
            txt_filename = f"{stem}.extracted.txt"
            txt_path = config.GENERATED_DIR / txt_filename
            if txt_path.exists():
                txt_filename = f"{stem}_{uuid.uuid4().hex[:8]}.extracted.txt"
                txt_path = config.GENERATED_DIR / txt_filename

            txt_path.parent.mkdir(parents=True, exist_ok=True)

            method = outcome.method or "unspecified"
            header_lines = [
                f"# Raster: generated/images/{safe_name}",
                f"# MIME type: {mime}",
                f"# ingestion_method: {method}",
                "",
            ]
            kb_gemini_visual = (
                "# kb_gemini_visual: yes\n"
                if outcome.has_visual_understanding
                else "# kb_gemini_visual: no\n"
            )

            headline_map = {
                "gemini_visual_plus_tesseract": (
                    "Indexed Gemini Vision scene description plus Tesseract OCR text."
                ),
                "quota_tesseract_ocr": (
                    "Indexed OCR text only (Gemini Vision quota unavailable)."
                ),
                "gemini_empty_tesseract_ocr": (
                    "Indexed OCR text only (Gemini Vision returned no description)."
                ),
                "local_tesseract_only": (
                    "Indexed OCR text only (Gemini Vision not configured)."
                ),
            }
            headline = headline_map.get(
                method,
                "Image processed and queued for indexing.",
            )
            if outcome.method == "quota_tesseract_ocr":
                message_extra = (
                    "OCR text indexed; visual scene/object questions require Gemini Vision "
                    "quota — poll /api/status."
                )
            elif outcome.method == "local_tesseract_only":
                message_extra = (
                    "OCR glyphs indexed only; configure Gemini Vision for visual "
                    "descriptions — poll /api/status."
                )
            elif outcome.method == "gemini_empty_tesseract_ocr":
                message_extra = (
                    "OCR indexed; Gemini did not emit a VISUAL DESCRIPTION — poll "
                    "/api/status."
                )
            elif outcome.method == "gemini_visual_plus_tesseract":
                message_extra = (
                    "VISUAL DESCRIPTION + OCR saved; poll /api/status until ready=true."
                )
            else:
                message_extra = (
                    "Processing complete; poll /api/status until ready=true."
                )

            header_text = "\n".join(header_lines)

            notices = ""
            if outcome.upload_notice:
                notices = outcome.upload_notice.strip() + "\n\n"

            txt_path.write_text(
                header_text
                + kb_flag
                + kb_gemini_visual
                + notices
                + outcome.text
                + "\n",
                encoding="utf-8",
            )
            txt_rel = txt_path.relative_to(config.DATA_DIR).as_posix()
            stored_paths.append(txt_rel)
            size = txt_path.stat().st_size
            if outcome.upload_notice:
                upload_followup_note = "\n\n" + outcome.upload_notice.strip()

        else:
            return jsonify({"error": "Unsupported upload path."}), 400

    except OSError as exc:
        return jsonify({"error": f"Failed to save file: {exc}"}), 500

    threading.Thread(
        target=_reindex_engine_background, daemon=True, name="rag-reindex"
    ).start()

    primary_name = stored_paths[-1] if ext in IMAGE_UPLOAD_EXTENSIONS else stored_paths[0]

    return jsonify({
        "ok": True,
        "filename": primary_name,
        "stored_paths": stored_paths,
        "size": size,
        "message": f"{headline} Re-indexing in the background; {message_extra}"
        + upload_followup_note,
    }), 201


@app.route("/api/reset-all", methods=["POST"])
def api_reset_all():
    """Destructive wipe: clears SQLite chats + uploads except starter PDFs."""
    global _init_error

    payload = request.get_json(silent=True) or {}
    if not payload.get("confirm"):
        return jsonify({"error": 'Send JSON {"confirm": true} to proceed.'}), 400

    if not GEMINI_API_KEY or not HF_TOKEN:
        return jsonify({"error": "API keys missing; cannot rebuild the index."}), 503

    try:
        database.clear_all_conversations()
        _reset_project_disk_and_cache()
        database.vacuum_database_file()
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500

    threading.Thread(
        target=_reindex_engine_background, daemon=True, name="rag-reset-reindex"
    ).start()

    return jsonify({
        "ok": True,
        "message": (
            "SQLite conversations cleared; uploads removed; "
            "starter knowledge-base files preserved; sample fixture archived under "
            f"'sample_uploads/{SAMPLE_FIXTURE_PDF}' when present; "
            "index rebuilding."
        ),
    }), 200


@app.route("/api/session-uploads/reset", methods=["POST"])
def api_reset_session_uploads():
    """Drop conversation-scoped uploads; rebuild index from starter ``data/`` files."""
    global _init_error

    if not GEMINI_API_KEY or not HF_TOKEN:
        return jsonify({"error": "API keys missing; cannot rebuild the index."}), 503

    try:
        _reset_kb_to_starters()
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500

    threading.Thread(
        target=_reindex_engine_background, daemon=True, name="rag-session-reset-reindex"
    ).start()

    return jsonify({
        "ok": True,
        "message": "Session uploads removed; knowledge base reset to starter files.",
    }), 200


# ---------- sessions ----------

@app.route("/api/sessions", methods=["GET"])
def api_list_sessions():
    return jsonify({"sessions": database.list_sessions()})


@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "New conversation").strip() or "New conversation"
    session = database.create_session(title=title)
    return jsonify(session), 201


@app.route("/api/sessions/<session_id>", methods=["GET"])
def api_get_session(session_id):
    session = database.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    session["messages"] = database.get_messages(session_id)
    return jsonify(session)


@app.route("/api/sessions/<session_id>", methods=["PATCH"])
def api_update_session(session_id):
    if not database.get_session(session_id):
        return jsonify({"error": "Session not found"}), 404
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    database.update_session_title(session_id, title)
    return jsonify(database.get_session(session_id))


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    if not database.get_session(session_id):
        return jsonify({"error": "Session not found"}), 404
    database.delete_session(session_id)
    return jsonify({"ok": True})


# ---------- chat ----------

@app.route("/api/sessions/<session_id>/messages", methods=["POST"])
def api_send_message(session_id):
    if _init_error is not None:
        return jsonify({
            "error": _init_error["message"],
            "status": engine.status,
            "init_failed": True,
        }), 503

    if not engine.ready:
        return jsonify({
            "error": "RAG engine is still initialising. Please wait.",
            "status": engine.status,
        }), 503

    session = database.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    payload = request.get_json(silent=True) or {}
    question = (payload.get("content") or "").strip()
    if not question:
        return jsonify({"error": "content is required"}), 400

    history = database.get_history_for_llm(session_id, limit=20)
    user_msg = database.add_message(session_id, "user", question)

    try:
        result = engine.answer(question=question, history=history)
    except Exception:
        traceback.print_exc()
        return jsonify({
            "error": (
                "The assistant could not finish that reply due to an unexpected "
                "error. Try again shortly. "
                "If you recently saw quota or rate-limit messages from Gemini, "
                "waiting a few minutes often clears them; check container logs "
                "if it keeps failing."
            ),
            "user_message": user_msg,
        }), 503

    assistant_msg = database.add_message(
        session_id,
        "assistant",
        result["answer"],
        context=result["context"],
    )

    if session["title"] == "New conversation":
        new_title = question[:60] + ("..." if len(question) > 60 else "")
        database.update_session_title(session_id, new_title)

    return jsonify({
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "refused": result.get("refused", False),
    })


# ==========================================================
# ENTRY POINT
# ==========================================================

_start_background_init()


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
