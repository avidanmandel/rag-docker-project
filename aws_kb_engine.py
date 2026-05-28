"""
Amazon Bedrock Knowledge Base backend (optional).

Used when ``RAG_BACKEND=aws_kb``. Queries the managed KB via
``bedrock-agent-runtime``; does not use local FAISS, ``data/``, Hugging Face,
or Gemini.
"""

from __future__ import annotations

import threading
from typing import Any

import boto3

import config

AWS_KB_MODE_MSG = (
    "AWS Knowledge Base mode uses AWS data. "
    "Upload files to S3 and sync the Knowledge Base in AWS."
)


class AWSKnowledgeBaseEngine:
    """Bedrock Knowledge Base retrieve-and-generate backend."""

    def __init__(self) -> None:
        self.chunks: list = []
        self.ready: bool = False
        self.status: str = "not_initialised"
        self.progress: dict = {"current": 0, "total": 0}
        self._lock = threading.Lock()
        self._client: Any = None

    def initialise(self) -> None:
        kb_id = (config.BEDROCK_KB_ID or "").strip()
        model_arn = (config.BEDROCK_MODEL_ARN or "").strip()
        if not kb_id:
            raise ValueError("BEDROCK_KB_ID must be set when RAG_BACKEND=aws_kb.")
        if not model_arn:
            raise ValueError("BEDROCK_MODEL_ARN must be set when RAG_BACKEND=aws_kb.")

        with self._lock:
            if self.ready:
                return
            self.status = "initialising"
            self.progress = {"current": 0, "total": 1}
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=config.AWS_REGION,
            )
            self.ready = True
            self.status = "ready"
            self.progress = {"current": 1, "total": 1}

    def reindex(self) -> None:
        """Local reindex is not applicable; KB data is managed in AWS."""
        with self._lock:
            self.status = "ready"
            self.ready = True
            self.progress = {"current": 1, "total": 1}

    def answer(
        self,
        question: str,
        history: list | None = None,
        k: int | None = None,
    ) -> dict:
        if not question or not question.strip():
            return {
                "answer": "Please type a real question.",
                "context": [],
                "refused": True,
                "reason": "empty_question",
            }

        if not self.ready or self._client is None:
            raise RuntimeError("AWS Knowledge Base engine is not ready yet.")

        top_k = k if k is not None else config.AWS_KB_TOP_K
        _ = history  # Bedrock KB RAG uses retrieve_and_generate in one call

        response = self._client.retrieve_and_generate(
            input={"text": question.strip()},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": config.BEDROCK_KB_ID.strip(),
                    "modelArn": config.BEDROCK_MODEL_ARN.strip(),
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": top_k,
                        }
                    },
                },
            },
        )

        answer_text = (
            response.get("output", {}).get("text", "").strip()
        )
        sources = _extract_sources_from_citations(response.get("citations", []))

        return {
            "answer": answer_text or "No answer was returned from the Knowledge Base.",
            "context": sources,
            "refused": False,
            "reason": None,
        }


def _extract_sources_from_citations(citations: list) -> list[dict]:
    """Build context entries compatible with the Flask UI (source, text, page)."""
    sources: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for citation in citations or []:
        refs = citation.get("retrievedReferences") or citation.get(
            "retrieved_references", []
        )
        for ref in refs:
            content = ref.get("content") or {}
            text = (content.get("text") or "").strip()

            location = ref.get("location") or {}
            s3_uri, location_label = _location_fields(location)

            key = (s3_uri or location_label, text[:200])
            if key in seen:
                continue
            seen.add(key)

            sources.append({
                "text": text,
                "source": s3_uri or location_label or "aws_kb",
                "page": 0,
                "score": 1.0,
                "location": location_label,
                "s3_uri": s3_uri,
            })

    return sources


def _location_fields(location: dict) -> tuple[str, str]:
    """Return (s3_uri, human-readable location label)."""
    loc_type = location.get("type", "")
    parts: list[str] = []

    s3 = location.get("s3Location") or location.get("s3_location") or {}
    uri = (s3.get("uri") or "").strip()
    if uri:
        parts.append(uri)

    web = location.get("webLocation") or location.get("web_location") or {}
    if web.get("url"):
        parts.append(str(web["url"]))

    confluence = location.get("confluenceLocation") or location.get(
        "confluence_location", {}
    )
    if confluence:
        parts.append(f"confluence:{confluence}")

    sharepoint = location.get("sharePointLocation") or location.get(
        "share_point_location", {}
    )
    if sharepoint:
        parts.append(f"sharepoint:{sharepoint}")

    custom = location.get("customDocumentLocation") or location.get(
        "custom_document_location", {}
    )
    if custom.get("id"):
        parts.append(str(custom["id"]))

    label = " | ".join(parts) if parts else (loc_type or "unknown")
    return uri, label
