"""
RAG engine: PDF loading, character chunking, Hugging Face embeddings,
FAISS vector search, and Gemini grounded generation.

The engine is built once at app startup and held in memory. The FAISS
index + chunk metadata are also persisted to ``index_cache/`` so subsequent
restarts skip the slow embedding step.
"""

from __future__ import annotations

import json
import pickle
import threading
import time
from pathlib import Path

import faiss
import numpy as np
from google import genai
from google.genai import types
from huggingface_hub import InferenceClient

import config
from chunker import Chunk, chunk_pages
from pdf_loader import load_folder


def _log(msg: str) -> None:
    print(f"[rag] {msg}", flush=True)


REFUSAL_TEXT = (
    "I don't have enough information in the course materials "
    "(Flask lectures, Docker/AWS notes) to answer that."
)


# ==========================================================
# Helpers
# ==========================================================

def _normalize_embedding_output(raw_output, expected_count: int) -> np.ndarray:
    """Coerce HF feature_extraction output into shape (expected_count, dim)."""
    arr = np.array(raw_output, dtype="float32")

    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    elif arr.ndim == 2:
        if arr.shape[0] == expected_count:
            pass
        elif expected_count == 1:
            arr = arr.mean(axis=0, keepdims=True)
        else:
            raise ValueError(
                f"Unexpected 2D embedding shape: {arr.shape}, "
                f"expected_count={expected_count}"
            )
    elif arr.ndim == 3:
        arr = arr.mean(axis=1)
    else:
        raise ValueError(f"Unexpected embedding dimensions: {arr.ndim}")

    if arr.shape[0] != expected_count:
        raise ValueError(
            f"Embedding count mismatch. Expected {expected_count}, "
            f"got {arr.shape[0]}"
        )
    return arr.astype("float32")


# ==========================================================
# RAGEngine
# ==========================================================

class RAGEngine:
    """Encapsulates the whole RAG pipeline as one process-wide object."""

    INDEX_FILE = "faiss.index"
    META_FILE = "meta.pkl"
    MANIFEST_FILE = "manifest.json"

    def __init__(self) -> None:
        self.data_dir: Path = config.DATA_DIR
        self.cache_dir: Path = config.INDEX_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.chunks: list[Chunk] = []
        self.index: faiss.Index | None = None
        self.ready: bool = False
        self.status: str = "not_initialised"
        self.progress: dict = {"current": 0, "total": 0}

        self._lock = threading.Lock()

        self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.hf_client = InferenceClient(
            provider="hf-inference", api_key=config.HF_TOKEN
        )

    # ---------- initialisation ----------

    def initialise(self) -> None:
        with self._lock:
            if self.ready:
                return

            manifest = self._current_manifest()

            if self._cache_matches(manifest):
                self.status = "loading_cache"
                _log("Loading FAISS index from cache...")
                self._load_cache()
                self.ready = True
                self.status = "ready"
                _log(
                    f"Ready (from cache). {self.index.ntotal} vectors, "
                    f"{len({c.source for c in self.chunks})} document(s)."
                )
                return

            self.status = "loading_documents"
            _log(f"Loading PDFs from '{self.data_dir}'...")
            pages = load_folder(self.data_dir)
            _log(f"Extracted text from {len(pages)} page(s).")

            self.status = "chunking_documents"
            self.chunks = chunk_pages(
                pages,
                chunk_size=config.CHUNK_SIZE,
                chunk_overlap=config.CHUNK_OVERLAP,
            )
            _log(f"Produced {len(self.chunks)} chunks.")

            self.status = "embedding_documents"
            _log("Embedding chunks via Hugging Face Inference API...")
            embeddings = self._embed_texts([c.text for c in self.chunks])

            self.status = "building_index"
            _log("Building FAISS index...")
            self.index = self._create_faiss_index(embeddings)

            self.status = "saving_cache"
            self._save_cache(manifest)

            self.ready = True
            self.status = "ready"
            _log(f"Ready. {self.index.ntotal} vectors indexed.")

    # ---------- embeddings ----------

    def _hf_with_retries(self, inputs, expected_count: int, max_retries: int = 5):
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                raw = self.hf_client.feature_extraction(
                    inputs, model=config.HF_EMBEDDING_MODEL
                )
                return _normalize_embedding_output(raw, expected_count)
            except Exception as exc:
                last_error = exc
                _log(
                    f"Embedding call failed "
                    f"(attempt {attempt}/{max_retries}): {exc}"
                )
                if attempt == max_retries:
                    raise
                time.sleep(attempt * 3)
        raise RuntimeError(f"Embedding failed: {last_error}")

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        batch_size = config.EMBED_BATCH_SIZE
        total_batches = (len(texts) + batch_size - 1) // batch_size
        self.progress = {"current": 0, "total": total_batches}

        all_embeddings: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            batch_num = start // batch_size + 1
            _log(f"  batch {batch_num}/{total_batches} ({len(batch)} items)...")
            embeddings = self._hf_with_retries(batch, expected_count=len(batch))
            all_embeddings.append(embeddings)
            self.progress = {"current": batch_num, "total": total_batches}

        return np.vstack(all_embeddings).astype("float32")

    def _embed_query(self, query: str) -> np.ndarray:
        return self._hf_with_retries(query, expected_count=1).astype("float32")

    # ---------- FAISS ----------

    @staticmethod
    def _create_faiss_index(embeddings: np.ndarray) -> faiss.Index:
        faiss.normalize_L2(embeddings)
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        return index

    def retrieve(self, query: str, k: int | None = None) -> list[dict]:
        if not self.ready:
            raise RuntimeError("RAG engine is not ready yet.")
        k = k or config.TOP_K

        q = self._embed_query(query)
        faiss.normalize_L2(q)
        scores, indexes = self.index.search(q, k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indexes[0]):
            if idx == -1:
                continue
            chunk = self.chunks[idx]
            results.append({
                "text": chunk.text,
                "source": chunk.source,
                "page": chunk.page,
                "score": float(score),
            })
        return results

    # ---------- Gemini ----------

    def _build_prompt(self, context: str, question: str, history_text: str) -> str:
        return f"""You are a course assistant for a class on Flask, Docker, and AWS.

You must answer strictly from the provided context, which was retrieved from the
official course materials (Flask lectures, Docker & AWS notes).

Rules:
1. Use ONLY the information in the context. Do not use outside knowledge.
2. If the context does not contain enough information to answer the question,
   reply EXACTLY with:
   "{REFUSAL_TEXT}"
3. Do not invent file names, commands, URLs, or quotes.
4. Keep answers concise, structured, and beginner-friendly. Use short bullet
   points when listing steps or options.
5. Use the conversation history ONLY to resolve references like "it" or
   "that command" - never invent earlier turns.

Conversation so far:
{history_text or "(no previous messages)"}

Context retrieved from the course materials:
\"\"\"
{context}
\"\"\"

User's question:
{question}

Answer (grounded in the context above):
"""

    def _ask_gemini(self, prompt: str) -> str:
        response = self.gemini_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=600,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return (response.text or "").strip()

    # ---------- high level ----------

    def answer(
        self,
        question: str,
        history: list[dict] | None = None,
        k: int | None = None,
    ) -> dict:
        """Retrieve + (optionally) generate. Always returns a structured dict."""
        if not question or not question.strip():
            return {
                "answer": "Please type a real question.",
                "context": [],
                "refused": True,
                "reason": "empty_question",
            }

        retrieved = self.retrieve(question, k=k)

        relevant = [r for r in retrieved if r["score"] >= config.MIN_SCORE_THRESHOLD]
        if not relevant:
            return {
                "answer": REFUSAL_TEXT,
                "context": retrieved,
                "refused": True,
                "reason": "low_similarity",
            }

        context_text = "\n\n---\n\n".join(
            f"[{r['source']} p.{r['page']}] {r['text']}" for r in relevant
        )

        history_text = ""
        if history:
            lines = []
            for msg in history:
                role = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"{role}: {msg['content']}")
            history_text = "\n".join(lines)

        prompt = self._build_prompt(
            context=context_text, question=question, history_text=history_text
        )
        answer_text = self._ask_gemini(prompt)

        return {
            "answer": answer_text or REFUSAL_TEXT,
            "context": retrieved,
            "refused": answer_text.strip() == REFUSAL_TEXT,
            "reason": None,
        }

    # ---------- cache ----------

    def _current_manifest(self) -> dict:
        """Fingerprint of inputs that should invalidate the cached index."""
        files = []
        for p in sorted(self.data_dir.glob("*")):
            if p.is_file() and p.suffix.lower() in {".pdf", ".txt"}:
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                })
        return {
            "files": files,
            "chunk_size": config.CHUNK_SIZE,
            "chunk_overlap": config.CHUNK_OVERLAP,
            "model": config.HF_EMBEDDING_MODEL,
        }

    def _cache_matches(self, manifest: dict) -> bool:
        manifest_path = self.cache_dir / self.MANIFEST_FILE
        index_path = self.cache_dir / self.INDEX_FILE
        meta_path = self.cache_dir / self.META_FILE
        if not (manifest_path.exists() and index_path.exists() and meta_path.exists()):
            return False
        try:
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return saved == manifest

    def _save_cache(self, manifest: dict) -> None:
        faiss.write_index(self.index, str(self.cache_dir / self.INDEX_FILE))
        with open(self.cache_dir / self.META_FILE, "wb") as fh:
            pickle.dump([c.as_dict() for c in self.chunks], fh)
        (self.cache_dir / self.MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _load_cache(self) -> None:
        self.index = faiss.read_index(str(self.cache_dir / self.INDEX_FILE))
        with open(self.cache_dir / self.META_FILE, "rb") as fh:
            raw = pickle.load(fh)
        self.chunks = [Chunk(**item) for item in raw]
