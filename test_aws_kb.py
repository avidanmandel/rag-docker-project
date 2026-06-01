"""
Manual test for ScoutMatch AI — AWS Bedrock Knowledge Base mode.

Requires:
  - RAG_BACKEND=aws_kb in .env (or environment)
  - BEDROCK_KB_ID set
  - AWS credentials (e.g. ~/.aws/credentials)

Does not print secret values.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

if os.getenv("RAG_BACKEND", "local").strip().lower() != "aws_kb":
    print("Set RAG_BACKEND=aws_kb in .env to run this test.")
    sys.exit(0)

if not (os.getenv("BEDROCK_KB_ID") or "").strip():
    print("BEDROCK_KB_ID is not set in .env — skipping AWS KB test.")
    sys.exit(0)

import config  # noqa: E402
from aws_kb_engine import AWSKnowledgeBaseEngine  # noqa: E402

TEST_QUESTION = (
    "Which goalkeeper is most suitable for build-up play from the back?"
)


def main() -> None:
    engine = AWSKnowledgeBaseEngine()
    print("Initialising AWS Knowledge Base engine...")
    engine.initialise()
    print(f"Status: {engine.status}, ready={engine.ready}")

    print(f"\nQuestion: {TEST_QUESTION}\n")
    result = engine.answer(question=TEST_QUESTION)

    print("--- Answer ---")
    print(result.get("answer", ""))

    sources = result.get("context") or []
    print(f"\n--- Sources ({len(sources)}) ---")
    for i, src in enumerate(sources, 1):
        uri = src.get("s3_uri") or src.get("source") or ""
        loc = src.get("location") or ""
        preview = (src.get("text") or "")[:200]
        print(f"[{i}] location={loc}")
        if uri:
            print(f"    s3_uri={uri}")
        if preview:
            print(f"    text_preview={preview!r}")


if __name__ == "__main__":
    main()
