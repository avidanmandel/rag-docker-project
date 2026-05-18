"""
End-to-end smoke test for the RAG pipeline.

Initialises the RAG engine (using the cached FAISS index when present) and
runs a curated list of test questions, printing for each:
    - the answer text
    - the refusal flag
    - the top retrieved chunks (file, page, score)

Run with:
    python tests/test_rag.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

# Make ``rag_course_assistant/`` importable when this file is run directly.
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag_engine import RAGEngine  # noqa: E402


TEST_QUESTIONS: list[tuple[str, str]] = [
    ("What is Flask?", "in_scope"),
    ("How do I define a route in Flask?", "in_scope"),
    (
        "What is a Docker container, and how is it different from a virtual machine?",
        "in_scope",
    ),
    ("How do I write a Dockerfile for a Flask application?", "in_scope"),
    (
        "What AWS services are mentioned for deploying a web application?",
        "in_scope",
    ),
    ("What is the capital of France?", "out_of_scope"),
]


def hr(char: str = "=", width: int = 78) -> str:
    return char * width


def main() -> int:
    print(hr())
    print("Initialising RAG engine (this may take a while on the first run)...")
    print(hr())

    engine = RAGEngine()
    engine.initialise()

    print(f"Engine ready: {engine.index.ntotal} vectors over "
          f"{len({c.source for c in engine.chunks})} document(s).\n")

    fails = 0

    for i, (question, expected) in enumerate(TEST_QUESTIONS, start=1):
        print(hr())
        print(f"Q{i}. {question}")
        print(f"    (expected: {expected})")
        print(hr("-"))

        result = engine.answer(question)

        for prefix_line in textwrap.wrap(
            result["answer"], width=78, initial_indent="A: ", subsequent_indent="   "
        ):
            print(prefix_line)

        print(f"\nrefused: {result['refused']}  reason: {result.get('reason')}")

        ok = (
            (expected == "out_of_scope" and result["refused"])
            or (expected == "in_scope" and not result["refused"])
        )
        verdict = "PASS" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"verdict: {verdict}")

        print("\nTop retrieved chunks:")
        for j, chunk in enumerate(result["context"][:4], start=1):
            snippet = chunk["text"].replace("\n", " ")
            if len(snippet) > 110:
                snippet = snippet[:110] + "..."
            print(
                f"  {j}. [{chunk['source']} p.{chunk['page']}] "
                f"score={chunk['score']:.3f}  {snippet}"
            )
        print()

    print(hr())
    total = len(TEST_QUESTIONS)
    print(f"Summary: {total - fails}/{total} passed.")
    print(hr())
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
