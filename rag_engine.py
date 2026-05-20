"""
RAG engine: document loading, character chunking, Hugging Face embeddings,
FAISS vector search, and Gemini grounded generation.

Strict RAG only: answers come exclusively from retrieved document chunks.
No general-knowledge fallback.
"""

from __future__ import annotations

import json
import pickle
import re
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
from image_extract import extract_image_text_for_rag
from pdf_loader import load_folder


def _log(msg: str) -> None:
    print(f"[rag] {msg}", flush=True)


_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_FILENAME_HINT_RE = re.compile(r"\b([\w\-]+\.(?:pdf|txt))\b", re.I)

# Retrieval-only bilingual aliases (English/typo -> Hebrew document terms).
_RETRIEVAL_ALIASES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("france", "franch", "french"), ("צרפת", "פריז")),
    (("capital city",), ("עיר בירה", "בירה")),
    (("capital",), ("עיר בירה", "בירה")),
    (("iceland",), ("איסלנד",)),
    (("germany",), ("גרמניה",)),
    (("spain",), ("ספרד",)),
    (("real madrid",), ("ריאל מדריד", "וריאל מדריד")),
    (("maccabi haifa",), ("מכבי חיפה",)),
    (("ronaldo",), ("רונאלדו", "כריסטיאנו רונאלדו")),
    (("messi",), ("מסי", "ליונל מסי")),
]


def _collect_query_alias_terms(query: str) -> tuple[str, list[str]]:
    """Return normalized query and Hebrew alias terms for bilingual matching."""
    normalized = re.sub(r"\bfranch\b", "france", query, flags=re.I)
    lowered = normalized.lower()
    extras: list[str] = []
    for en_terms, he_terms in _RETRIEVAL_ALIASES:
        for term in sorted(en_terms, key=len, reverse=True):
            if " " in term:
                matched = term in lowered
            else:
                matched = bool(re.search(rf"\b{re.escape(term)}\b", lowered))
            if matched:
                extras.extend(he_terms)
                break
    seen: set[str] = set()
    unique: list[str] = []
    for term in extras:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return normalized, unique


def _expand_query_for_retrieval(query: str) -> str:
    """Append Hebrew retrieval terms when English aliases appear in the query."""
    normalized, extras = _collect_query_alias_terms(query)
    if not extras:
        return query
    expanded = f"{normalized} {' '.join(extras)}"
    if re.search(r"\b(france|franch|french)\b", query, re.I):
        _log(f"Expanded retrieval query: {expanded}")
    return expanded


def _context_matches_query_aliases(question: str, context: str) -> bool:
    """True when Hebrew alias terms implied by the question appear in the context."""
    _, aliases = _collect_query_alias_terms(question)
    if not aliases:
        return False
    return any(term in context for term in aliases)


# English answer terms bridged to Hebrew/English tokens allowed in retrieved context.
_ANSWER_TO_CONTEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "paris": ("paris", "פריז"),
    "france": ("france", "צרפת"),
    "french": ("french", "צרפת"),
}


def _answer_terms_supported_in_context(answer: str, context: str) -> bool:
    """Check whether English answer terms are supported via bilingual aliases."""
    ctx_lower = context.lower()
    for en_term, ctx_terms in _ANSWER_TO_CONTEXT_ALIASES.items():
        if re.search(rf"\b{re.escape(en_term)}\b", answer, re.I):
            if any(t in context or t in ctx_lower for t in ctx_terms):
                return True
    return False


def _known_typo_fix(question: str) -> str:
    """Fix common query typos for grounded generation (retrieval unchanged)."""
    return re.sub(r"\bfranch\b", "france", question, flags=re.I)


def _filename_hint(question: str) -> str | None:
    match = _FILENAME_HINT_RE.search(question)
    if not match:
        return None
    return match.group(1).strip()


def _filter_retrieved_for_hint(
    retrieved: list[dict],
    hint: str | None,
    limit: int,
    all_chunks: list | None = None,
) -> list[dict]:
    if not hint or not retrieved:
        return retrieved[:limit]
    needle = hint.lower()
    hinted = [
        r for r in retrieved
        if needle in Path(r["source"]).name.lower()
    ]
    if hinted:
        return hinted[:limit]
    if all_chunks:
        hinted = [
            {
                "text": c.text,
                "source": c.source,
                "page": c.page,
                "score": 0.0,
            }
            for c in all_chunks
            if needle in Path(c.source).name.lower()
        ]
        if hinted:
            return hinted[:limit]
    return retrieved[:limit]


def _is_hebrew(question: str) -> bool:
    return bool(_HEBREW_RE.search(question))


def _refusal_text(question: str) -> str:
    if _is_hebrew(question):
        return config.REFUSAL_TEXT_HE
    return config.REFUSAL_TEXT_EN


def _no_kb_text(question: str) -> str:
    if _is_hebrew(question):
        return config.NO_KB_TEXT_HE
    return config.NO_KB_TEXT_EN


def _has_indexed_documents(engine: RAGEngine) -> bool:
    return bool(
        engine.chunks
        and engine.index is not None
        and engine.index.ntotal > 0
    )


def _answer_supported_by_context(
    answer: str,
    relevant: list[dict],
    *,
    question: str | None = None,
    filename_hint: str | None = None,
) -> bool:
    """Reject obvious general-knowledge leaks not present in retrieved text."""
    ctx = "\n".join(r["text"] for r in relevant)
    ctx_lower = ctx.lower()
    ans = answer.lower()

    if (
        filename_hint
        and relevant
        and all(
            filename_hint.lower() in Path(r["source"]).name.lower()
            for r in relevant
        )
    ):
        return True

    if question and _context_matches_query_aliases(question, ctx):
        if _HEBREW_RE.search(answer):
            he_words = [
                w for w in re.findall(r"[\u0590-\u05FF]+", answer) if len(w) > 2
            ]
            if he_words and any(w in ctx for w in he_words):
                return True
        if _answer_terms_supported_in_context(answer, ctx):
            return True

    if "paris" in ans and "paris" not in ctx_lower and "פריז" not in ctx:
        return False
    if "פריז" in answer and "פריז" not in ctx:
        return False

    nums = re.findall(r"\d+", answer)
    if nums and any(n in ctx for n in nums):
        return True

    if _HEBREW_RE.search(answer):
        he_words = [w for w in re.findall(r"[\u0590-\u05FF]+", answer) if len(w) > 2]
        if he_words and any(w in ctx for w in he_words):
            return True

    tokens = [
        t
        for t in re.findall(r"[a-z]{5,}", ans)
        if t not in {"according", "based", "source", "document", "report"}
    ]
    if not tokens:
        return True
    return any(t in ctx_lower for t in tokens)


def _looks_like_refusal(answer: str) -> bool:
    lowered = answer.strip().lower()
    if not lowered:
        return True
    markers = (
        "do not have enough information",
        "don't have enough information",
        "not enough information",
        "cannot answer",
        "can't answer",
        "no information",
        "אין לי מספיק מידע",
    )
    return any(m in lowered for m in markers)


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

    def __init__(
        self,
        gemini_api_key: str | None = None,
        hf_token: str | None = None,
    ) -> None:
        self.data_dir: Path = config.DATA_DIR
        self.cache_dir: Path = config.INDEX_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.chunks: list[Chunk] = []
        self.index: faiss.Index | None = None
        self.ready: bool = False
        self.status: str = "not_initialised"
        self.progress: dict = {"current": 0, "total": 0}

        self._lock = threading.Lock()

        self._gemini_api_key = gemini_api_key or config.GEMINI_API_KEY
        self._hf_token = hf_token or config.HF_TOKEN
        self.gemini_client = None
        self.hf_client = None

    def _ensure_clients(self) -> None:
        if not self._gemini_api_key or not self._hf_token:
            raise ValueError(
                "GEMINI_API_KEY and HF_TOKEN must be set in .env before "
                "initialising the RAG engine."
            )
        if self.gemini_client is None:
            self.gemini_client = genai.Client(api_key=self._gemini_api_key)
        if self.hf_client is None:
            self.hf_client = InferenceClient(
                provider="hf-inference", api_key=self._hf_token
            )

    # ---------- initialisation ----------

    def initialise(self) -> None:
        self._ensure_clients()
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
                    f"Ready (from cache). "
                    f"{self.index.ntotal if self.index else 0} vectors, "
                    f"{len({c.source for c in self.chunks})} document(s)."
                )
                return

            self._build_index(manifest)

    def reindex(self) -> None:
        """Drop cache and rebuild the FAISS index from ``data/``."""
        with self._lock:
            self.ready = False
            self.status = "reindexing"
            self.chunks = []
            self.index = None
            for name in (self.INDEX_FILE, self.META_FILE, self.MANIFEST_FILE):
                path = self.cache_dir / name
                if path.is_file():
                    path.unlink()

        self.initialise()

    def _build_index(self, manifest: dict) -> None:
        self.status = "loading_documents"
        _log(f"Loading documents from '{self.data_dir}'...")
        pages = load_folder(self.data_dir)
        _log(f"Extracted text from {len(pages)} page(s).")

        self.status = "chunking_documents"
        self.chunks = chunk_pages(
            pages,
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )
        _log(f"Produced {len(self.chunks)} chunks.")

        if not self.chunks:
            self.index = None
            self.ready = True
            self.status = "ready"
            self._save_cache(manifest)
            _log("Ready with an empty knowledge base (no documents indexed).")
            return

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

    def extract_image_for_kb(self, image_bytes: bytes, mime_type: str):
        """Run Gemini Vision + OCR pipeline for image uploads."""
        self._ensure_clients()
        return extract_image_text_for_rag(
            self.gemini_client,
            config.GEMINI_MODEL,
            image_bytes,
            mime_type,
        )

    # ---------- embeddings ----------

    def _hf_with_retries(self, inputs, expected_count: int, max_retries: int = 5):
        self._ensure_clients()
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
        if not _has_indexed_documents(self):
            return []
        k = k or config.TOP_K

        retrieval_query = _expand_query_for_retrieval(query)
        q = self._embed_query(retrieval_query)
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

    def _build_prompt(
        self,
        context: str,
        question: str,
        history_text: str,
        refusal_text: str,
    ) -> str:
        return f"""You are a strict document assistant. You answer ONLY from the
retrieved context below. The context comes from files in the knowledge base.

Rules:
1. Use ONLY the information in the context. Do NOT use outside or general knowledge.
2. Do NOT guess, invent, or hallucinate facts, file names, commands, or quotes.
3. If the context does not contain enough information to answer the question,
   reply EXACTLY with this sentence (nothing else):
   "{refusal_text}"
4. When you do answer, cite the source file and page when possible
   (e.g. "According to docker_aws.pdf p.3 …").
5. Keep answers concise and structured. Use short bullet points when listing items.
6. Use the conversation history ONLY to resolve references like "it" or
   "that command" — never invent earlier turns.

Conversation so far:
{history_text or "(no previous messages)"}

Context retrieved from the knowledge base:
\"\"\"
{context}
\"\"\"

User's question:
{question}

Answer (grounded strictly in the context above):
"""

    def _ask_gemini(self, prompt: str) -> str:
        self._ensure_clients()
        response = self.gemini_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
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
        """Retrieve relevant chunks, then generate a grounded answer."""
        refusal = _refusal_text(question)
        no_kb = _no_kb_text(question)

        if not question or not question.strip():
            return {
                "answer": "Please type a real question.",
                "context": [],
                "refused": True,
                "reason": "empty_question",
            }

        if not _has_indexed_documents(self):
            return {
                "answer": no_kb,
                "context": [],
                "refused": True,
                "reason": "no_knowledge_base",
            }

        hint = _filename_hint(question)
        retrieved = self.retrieve(
            question,
            k=(k or config.TOP_K) * 4 if hint else k,
        )
        retrieved = _filter_retrieved_for_hint(
            retrieved,
            hint,
            k or config.TOP_K,
            all_chunks=self.chunks,
        )
        relevant = [
            r for r in retrieved if r["score"] >= config.MIN_SCORE_THRESHOLD
        ]
        if question:
            seen = {id(r) for r in relevant}
            for r in retrieved:
                if id(r) not in seen and _context_matches_query_aliases(
                    question, r["text"]
                ):
                    relevant.append(r)
                    seen.add(id(r))
        if (
            hint
            and not relevant
            and retrieved
            and all(
                hint.lower() in Path(r["source"]).name.lower() for r in retrieved
            )
        ):
            relevant = retrieved

        if not relevant:
            return {
                "answer": refusal,
                "context": [],
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
            context=context_text,
            question=_known_typo_fix(question),
            history_text=history_text,
            refusal_text=refusal,
        )
        answer_text = self._ask_gemini(prompt)

        if not answer_text or _looks_like_refusal(answer_text):
            return {
                "answer": refusal,
                "context": [],
                "refused": True,
                "reason": "model_refusal",
            }

        if not _answer_supported_by_context(
            answer_text,
            relevant,
            question=question,
            filename_hint=hint,
        ):
            return {
                "answer": refusal,
                "context": [],
                "refused": True,
                "reason": "ungounded_answer",
            }

        cited = [
            r for r in relevant
            if Path(r["source"]).name in answer_text
        ]
        context_out = cited if cited else relevant

        return {
            "answer": answer_text,
            "context": context_out,
            "refused": False,
            "reason": None,
        }

    # ---------- cache ----------

    def _current_manifest(self) -> dict:
        """Fingerprint of inputs that should invalidate the cached index."""
        files = []
        for p in sorted(self.data_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".pdf", ".txt"}:
                rel = p.relative_to(self.data_dir).as_posix()
                stat = p.stat()
                files.append({
                    "name": rel,
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
        if not (manifest_path.exists() and meta_path.exists()):
            return False
        try:
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        if saved != manifest:
            return False
        with open(meta_path, "rb") as fh:
            cached_chunks = pickle.load(fh)
        if not cached_chunks:
            return not index_path.exists()
        return index_path.exists()

    def _save_cache(self, manifest: dict) -> None:
        if self.index is not None:
            faiss.write_index(self.index, str(self.cache_dir / self.INDEX_FILE))
        elif (self.cache_dir / self.INDEX_FILE).exists():
            (self.cache_dir / self.INDEX_FILE).unlink()
        with open(self.cache_dir / self.META_FILE, "wb") as fh:
            pickle.dump([c.as_dict() for c in self.chunks], fh)
        (self.cache_dir / self.MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _load_cache(self) -> None:
        with open(self.cache_dir / self.META_FILE, "rb") as fh:
            raw = pickle.load(fh)
        self.chunks = [Chunk(**item) for item in raw]
        index_path = self.cache_dir / self.INDEX_FILE
        self.index = (
            faiss.read_index(str(index_path)) if index_path.exists() else None
        )
